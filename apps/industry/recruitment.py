"""
Recruitment / manpower agency: client job orders, candidates and the placement pipeline
(CV sent → interview → selected → medical → visa → ticket → joined), the client's placement
fee, optional candidate processing fee, and the agency's own costs per placement.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .common import invoice as make_invoice, money, service_product
from .models import Candidate, JobOrder, Placement, PlacementCost

ZERO = Decimal("0")
STAGE_ORDER = [code for code, _label in Placement.STAGES]


def _number(obj, prefix):
    obj.number = f"{prefix}-{obj.pk:05d}"
    obj.save(update_fields=["number"])
    return obj


def create_job_order(*, company, user, client, **fields):
    if int(fields.get("vacancies") or 0) < 1:
        raise ValidationError("Enter how many people the client needs.")
    fields["fee_per_placement"] = money(fields.get("fee_per_placement"), "fee")
    job = JobOrder.objects.create(company=company, client=client, created_by=user, **fields)
    return _number(job, "JO")


def create_candidate(*, company, **fields):
    if not (fields.get("name") or "").strip():
        raise ValidationError("Enter the candidate's name.")
    passport = (fields.get("passport_no") or "").strip().upper()
    fields["passport_no"] = passport
    if passport and Candidate.objects.for_company(company).filter(passport_no__iexact=passport).exists():
        raise ValidationError(f"A candidate with passport {passport} already exists.")
    candidate = Candidate.objects.create(company=company, **fields)
    return _number(candidate, "CN")


def deployed_count(job):
    return job.placements.filter(stage="deployed").count()


@transaction.atomic
def submit(*, company, job, candidates):
    """Puts candidates forward for a job order. Returns (added, skipped names)."""
    if job.status in ("filled", "closed"):
        raise ValidationError("This job order is closed. Reopen it to add candidates.")
    added, skipped = [], []
    for candidate in candidates:
        if candidate.status == "not_suitable":
            skipped.append(candidate.name)
            continue
        try:
            with transaction.atomic():
                placement = Placement.objects.create(company=company, job_order=job, candidate=candidate,
                                                     fee=job.fee_per_placement, offered_salary=job.salary)
        except IntegrityError:
            skipped.append(candidate.name)
            continue
        added.append(placement)
        if candidate.status == "available":
            Candidate.objects.filter(pk=candidate.pk).update(status="in_process")
    return added, skipped


def _refresh_candidate_status(candidate):
    stages = set(candidate.placements.values_list("stage", flat=True))
    if "deployed" in stages:
        status = "placed"
    elif stages & set(Placement.ACTIVE):
        status = "in_process"
    elif candidate.status == "not_suitable":
        return
    else:
        status = "available"
    if candidate.status != status:
        Candidate.objects.filter(pk=candidate.pk).update(status=status)
        candidate.status = status


@transaction.atomic
def move(placement, stage, **fields):
    """Moves a placement to a stage and stores the details that belong to it."""
    if stage not in STAGE_ORDER:
        raise ValidationError("Unknown stage.")
    placement = Placement.objects.select_for_update().select_related("job_order", "candidate").get(pk=placement.pk)
    job = placement.job_order
    if stage == "deployed" and placement.stage != "deployed" and deployed_count(job) >= job.vacancies:
        raise ValidationError(f"All {job.vacancies} vacancies of {job.number} are already filled.")
    if stage == "medical" and fields.get("medical_result") == "unfit":
        stage = "rejected"
    for name, value in fields.items():
        if value is not None and hasattr(placement, name):
            setattr(placement, name, value)
    placement.stage = stage
    if stage == "deployed":
        placement.joining_date = placement.joining_date or timezone.localdate()
        placement.guarantee_until = placement.joining_date + timedelta(days=job.guarantee_days)
    placement.save()
    _refresh_candidate_status(placement.candidate)
    filled = deployed_count(job)
    if filled >= job.vacancies and job.status == "open":
        JobOrder.objects.filter(pk=job.pk).update(status="filled")
    elif filled < job.vacancies and job.status == "filled":
        JobOrder.objects.filter(pk=job.pk).update(status="open")
    return placement


@transaction.atomic
def bill_client(*, company, user, placement, amount=None, date=None):
    placement = Placement.objects.select_for_update().select_related("job_order__client", "candidate").get(pk=placement.pk)
    if placement.invoice_id:
        raise ValidationError("The client has already been billed for this placement.")
    fee = money(placement.fee if amount in (None, "") else amount, "fee")
    if fee <= 0:
        raise ValidationError("Enter the placement fee.")
    job = placement.job_order
    product = service_product(company, f"RECRUIT-FEE-{job.pk}", f"Placement fee · {job.position} ({job.number})")
    inv = make_invoice(company, user, job.client, [(product, 1, fee)], date=date)
    placement.fee, placement.invoice = fee, inv
    placement.save(update_fields=["fee", "invoice"])
    return inv


def candidate_customer(candidate):
    from apps.customers.models import Customer
    if candidate.customer_id:
        return candidate.customer
    customer = Customer.objects.create(company=candidate.company, name=candidate.name[:255], phone=(candidate.phone or "")[:20],
                                       email=candidate.email or "")
    Candidate.objects.filter(pk=candidate.pk).update(customer=customer)
    candidate.customer = customer
    return customer


@transaction.atomic
def bill_candidate(*, company, user, placement, amount, date=None):
    placement = Placement.objects.select_for_update().select_related("candidate", "job_order").get(pk=placement.pk)
    if placement.candidate_invoice_id:
        raise ValidationError("The candidate has already been billed for this placement.")
    fee = money(amount, "fee")
    if fee <= 0:
        raise ValidationError("Enter the candidate's fee.")
    product = service_product(company, "RECRUIT-PROC", "Processing / service charges")
    inv = make_invoice(company, user, candidate_customer(placement.candidate), [(product, 1, fee)], date=date)
    placement.candidate_fee, placement.candidate_invoice = fee, inv
    placement.save(update_fields=["candidate_fee", "candidate_invoice"])
    return inv


@transaction.atomic
def add_cost(*, company, user, placement, cost_type, amount, date=None, paid_to="", payment_method="cash"):
    from apps.expenses.models import ExpenseCategory
    from apps.expenses.services import record_expense
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Enter the amount paid.")
    if cost_type not in dict(PlacementCost.TYPES):
        raise ValidationError("Choose what the cost was for.")
    day = date or timezone.localdate()
    category, _ = ExpenseCategory.objects.get_or_create(company=company, name="Recruitment costs")
    label = dict(PlacementCost.TYPES)[cost_type]
    expense = record_expense(company=company, user=user, category=category, date=day, amount=amount,
                             payment_method=payment_method,
                             description=f"{label} · {placement.candidate.name} · {placement.job_order.number}"[:255])
    return PlacementCost.objects.create(company=company, placement=placement, cost_type=cost_type, amount=amount,
                                        date=day, paid_to=paid_to[:150], expense=expense)


def placement_money(placement):
    costs = placement.costs.aggregate(t=Sum("amount"))["t"] or ZERO
    income = (placement.fee if placement.invoice_id else ZERO) + (placement.candidate_fee if placement.candidate_invoice_id else ZERO)
    return {"costs": costs, "income": income, "profit": income - costs}


def pipeline_counts(company):
    rows = Placement.objects.for_company(company).values("stage").annotate(n=Count("id"))
    counts = {r["stage"]: r["n"] for r in rows}
    return [(code, label, counts.get(code, 0)) for code, label in Placement.STAGES]


def overview(company, today=None):
    today = today or timezone.localdate()
    jobs = JobOrder.objects.for_company(company)
    open_jobs = jobs.filter(status="open")
    placements = Placement.objects.for_company(company)
    month_start = today.replace(day=1)
    open_vacancies = 0
    for job in open_jobs.annotate(done=Count("placements", filter=Q(placements__stage="deployed"))):
        open_vacancies += max(job.vacancies - job.done, 0)
    return {
        "open_jobs": open_jobs.count(), "open_vacancies": open_vacancies,
        "candidates": Candidate.objects.for_company(company).count(),
        "available": Candidate.objects.for_company(company).filter(status="available").count(),
        "in_process": placements.filter(stage__in=Placement.ACTIVE).count(),
        "deployed_month": placements.filter(stage="deployed", joining_date__gte=month_start).count(),
        "fees_month": placements.filter(invoice__date__gte=month_start).aggregate(t=Sum("fee"))["t"] or ZERO,
        "to_bill": placements.filter(stage="deployed", invoice__isnull=True, fee__gt=0).count(),
        "interviews": placements.filter(stage="interview", interview_at__date__gte=today,
                                        interview_at__date__lte=today + timedelta(days=7))
                                .select_related("candidate", "job_order__client").order_by("interview_at")[:10],
        "passports": Candidate.objects.for_company(company).exclude(status__in=["placed", "not_suitable"])
                     .filter(passport_expiry__isnull=False, passport_expiry__lte=today + timedelta(days=180))
                     .order_by("passport_expiry")[:10],
        "visas": placements.filter(stage__in=["visa", "ticket"], visa_expiry__isnull=False,
                                   visa_expiry__lte=today + timedelta(days=30))
                           .select_related("candidate", "job_order").order_by("visa_expiry")[:10],
    }


# ------------------------------------------------------------------ nightly reminders

def daily_reminders(company, today=None):
    from apps.modules.catalog import business_features
    from apps.notifications.rules import once
    from apps.notifications.services import notify
    if "recruitment" not in business_features(company.business_type.code):
        return 0
    today = today or timezone.localdate()
    sent = 0
    for candidate in Candidate.objects.for_company(company).exclude(status__in=["placed", "not_suitable"]).filter(
            passport_expiry__isnull=False, passport_expiry__lte=today + timedelta(days=90)):
        level = "expired" if candidate.passport_expiry < today else "90"
        if once(company, f"rec-passport:{candidate.pk}:{candidate.passport_expiry}:{level}"):
            notify(company=company, title=f"Passport {'expired' if level == 'expired' else 'expiring'}: {candidate.name}",
                   message=f"Passport {candidate.passport_no or ''} expires on {candidate.passport_expiry:%d %b %Y}.")
            sent += 1
    for placement in Placement.objects.for_company(company).filter(stage__in=["visa", "ticket"], visa_expiry__isnull=False,
                                                                   visa_expiry__lte=today + timedelta(days=14)).select_related("candidate"):
        if once(company, f"rec-visa:{placement.pk}:{placement.visa_expiry}"):
            notify(company=company, title=f"Visa expiring before travel: {placement.candidate.name}",
                   message=f"Visa {placement.visa_number} expires on {placement.visa_expiry:%d %b %Y}. Book the ticket.")
            sent += 1
    for placement in Placement.objects.for_company(company).filter(stage="interview", interview_at__date=today).select_related("candidate", "job_order__client"):
        if once(company, f"rec-interview:{placement.pk}:{today}"):
            notify(company=company, title=f"Interview today: {placement.candidate.name}",
                   message=f"{placement.job_order.position} for {placement.job_order.client.name} at {timezone.localtime(placement.interview_at):%H:%M}.")
            sent += 1
    for placement in Placement.objects.for_company(company).filter(stage="deployed", guarantee_until=today + timedelta(days=7)).select_related("candidate", "job_order__client"):
        if once(company, f"rec-guarantee:{placement.pk}"):
            notify(company=company, title=f"Replacement guarantee ends in 7 days: {placement.candidate.name}",
                   message=f"{placement.job_order.client.name} · {placement.job_order.position}")
            sent += 1
    return sent
