"""Maintenance / service contracts (AMC).

A contract says: this customer (site / equipment) gets a visit every N weeks or months between two dates,
and pays up front, every month / 3 months / year, or per visit.

* Visits are made as job cards a week before they are due (daily job), so they show on the job board,
  the calendar and the technician's phone page like any other job.
* Monthly / quarterly / yearly billing is an ordinary recurring invoice (finance) that runs by itself;
  up-front billing makes one invoice when the contract is made; per-visit puts the visit price on each
  visit's job card, billed when the job is closed.
* Contracts ending in the next 30 days are listed for renewal (and the owner gets a notice once).
"""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.verticals.saloon.models import ServiceCase, ServiceContract

from . import jobs

AHEAD_DAYS = 7
MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "four_monthly": 4, "half_yearly": 6, "yearly": 12}
DAYS = {"weekly": 7, "fortnightly": 14}
BILL_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
CONTRACT_SKU = "AMC-SERVICE"


def step(day, every, anchor_day=None):
    from apps.finance.services import add_months
    if every in DAYS:
        return day + timedelta(days=DAYS[every])
    return add_months(day, MONTHS[every], anchor_day)


def visit_dates(start, end, every, limit=400):
    out, day = [], start
    while day <= end and len(out) < limit:
        out.append(day)
        day = step(day, every, start.day)
    return out


def months_between(start, end):
    """Whole months the contract covers: 12 Oct → 11 Oct next year is 12, 1 Oct → 30 Nov is 2."""
    months = (end.year - start.year) * 12 + end.month - start.month + (1 if end.day >= start.day else 0)
    return max(1, months)


def suggested_bill(value, billing, start, end, every):
    value = Decimal(value or 0)
    if billing == "upfront":
        return value
    if billing == "per_visit":
        count = len(visit_dates(start, end, every)) or 1
        return (value / count).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if billing in BILL_MONTHS:
        bills = max(1, -(-months_between(start, end) // BILL_MONTHS[billing]))
        return (value / bills).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return Decimal("0")


def _number(company):
    from apps.tenants.services import next_counter_value
    return f"AMC-{next_counter_value(company, 'service_contract'):05d}"


def _product(company, contract):
    from apps.industry.common import service_product
    return service_product(company, CONTRACT_SKU, "Maintenance contract")


@transaction.atomic
def create_contract(company, user, *, customer, title, start_date, end_date, visit_every="quarterly",
                    first_visit=None, preferred_time=None, visit_minutes=60, staff=None, visit_task="",
                    contract_value=Decimal("0"), billing="upfront", bill_amount=None, site_name="", site_address="",
                    identifier="", notes="", renewed_from=None):
    title = (title or "").strip()[:200]
    if len(title) < 2:
        raise ValidationError(_("Give the contract a name, e.g. AC maintenance – 4 units."))
    if end_date <= start_date:
        raise ValidationError(_("The end date must be after the start date."))
    if visit_every not in dict(ServiceContract.EVERY) or billing not in dict(ServiceContract.BILLING):
        raise ValidationError(_("Choose how often to visit and how to bill."))
    if staff is not None and staff.company_id != company.id:
        raise ValidationError(_("Choose your own staff member."))
    first_visit = first_visit or start_date
    if not (start_date <= first_visit <= end_date):
        raise ValidationError(_("The first visit must be inside the contract dates."))
    value = Decimal(contract_value or 0)
    if value < 0:
        raise ValidationError(_("Enter a valid amount."))
    amount = suggested_bill(value, billing, start_date, end_date, visit_every) if bill_amount in (None, "") \
        else Decimal(bill_amount)
    if amount < 0:
        raise ValidationError(_("Enter a valid amount."))
    today = timezone.localdate()
    while first_visit < today:  # a contract entered late: past visits are not made as job cards
        first_visit = step(first_visit, visit_every, start_date.day)
    first_visit = first_visit if first_visit <= end_date else None
    profile = jobs.profile_for(company, customer, site_name or title, identifier) if (site_name or identifier) else None
    contract = ServiceContract.objects.create(
        company=company, number=_number(company), customer=customer, profile=profile, title=title,
        site_address=(site_address or customer.address or "")[:2000], start_date=start_date, end_date=end_date,
        visit_every=visit_every, next_visit_date=first_visit, preferred_time=preferred_time,
        visit_minutes=max(5, min(int(visit_minutes or 60), 24 * 60)), staff=staff, visit_task=(visit_task or "")[:4000],
        contract_value=value, billing=billing, bill_amount=amount, notes=(notes or "")[:4000], created_by=user,
        renewed_from=renewed_from)
    _set_up_billing(contract, user)
    plan_visits(contract)
    return contract


def _set_up_billing(contract, user):
    company = contract.company
    if contract.billing == "upfront" and contract.bill_amount > 0:
        from apps.sales.services import create_invoice
        contract.upfront_invoice = create_invoice(
            company=company, user=user, customer=contract.customer, date=contract.start_date,
            warehouse=jobs._warehouse(company),
            lines=[{"product": _product(company, contract), "quantity": 1, "unit_price": contract.bill_amount}])
        contract.save(update_fields=["upfront_invoice"])
    elif contract.billing in BILL_MONTHS and contract.bill_amount > 0:
        from apps.finance.models import RecurringInvoice, RecurringInvoiceLine
        rec = RecurringInvoice.objects.create(
            company=company, name=f"{contract.number} {contract.title}"[:120], customer=contract.customer,
            warehouse=jobs._warehouse(company), frequency=contract.billing, next_run_date=contract.start_date,
            anchor_day=contract.start_date.day, end_date=contract.end_date, created_by=user)
        RecurringInvoiceLine.objects.create(recurring=rec, product=_product(company, contract), quantity=1,
                                            unit_price=contract.bill_amount)
        contract.recurring = rec
        contract.save(update_fields=["recurring"])


def _visit_title(contract, number):
    return (_("%(title)s — visit %(n)s") % {"title": contract.title, "n": number})[:200]


@transaction.atomic
def plan_visits(contract, today=None, ahead=AHEAD_DAYS):
    """Makes the job cards of visits due in the next ``ahead`` days. Returns how many were made."""
    contract = ServiceContract.objects.select_for_update().get(pk=contract.pk)
    today = today or timezone.localdate()
    made = 0
    while (contract.status == "active" and contract.next_visit_date
           and contract.next_visit_date <= today + timedelta(days=ahead)):
        if contract.next_visit_date > contract.end_date:
            contract.next_visit_date = None
            break
        number = contract.visits.count() + 1
        when = timezone.make_aware(datetime.combine(contract.next_visit_date, contract.preferred_time or time(9, 0)))
        profile = contract.profile
        job = jobs.create_job(contract.company, customer=contract.customer, title=_visit_title(contract, number),
                              subject_name=profile.subject_name if profile else contract.title,
                              identifier=profile.identifier if profile else "", staff=contract.staff,
                              scheduled_at=when, duration=contract.visit_minutes,
                              description="\n".join(x for x in (contract.visit_task, contract.site_address) if x),
                              case_type="contract visit")
        job.contract, job.visit_no = contract, number
        job.save(update_fields=["contract", "visit_no"])
        if contract.billing == "per_visit" and contract.bill_amount > 0:
            jobs.add_line(job, kind="labour", description=_("Contract visit %(n)s (%(number)s)") % {
                "n": number, "number": contract.number}, quantity=1, unit_price=contract.bill_amount)
        made += 1
        contract.next_visit_date = step(contract.next_visit_date, contract.visit_every, contract.start_date.day)
        if contract.next_visit_date > contract.end_date:
            contract.next_visit_date = None
    contract.save(update_fields=["next_visit_date"])
    return made


def upcoming_dates(contract, limit=8):
    """Visits still to be made (not yet a job card)."""
    out, day = [], contract.next_visit_date
    while day and day <= contract.end_date and len(out) < limit:
        out.append(day)
        day = step(day, contract.visit_every, contract.start_date.day)
    return out


def _recurring_active(contract, on):
    if contract.recurring_id:
        contract.recurring.is_active = on and contract.recurring.next_run_date <= contract.end_date
        contract.recurring.save(update_fields=["is_active"])


def pause(contract):
    if contract.status != "active":
        raise ValidationError(_("Only an active contract can be paused."))
    contract.status = "paused"
    contract.save(update_fields=["status"])
    _recurring_active(contract, False)


def resume(contract, today=None):
    if contract.status != "paused":
        raise ValidationError(_("This contract is not paused."))
    today = today or timezone.localdate()
    while contract.next_visit_date and contract.next_visit_date < today:  # missed visits while paused are skipped
        contract.next_visit_date = step(contract.next_visit_date, contract.visit_every, contract.start_date.day)
    if contract.next_visit_date and contract.next_visit_date > contract.end_date:
        contract.next_visit_date = None
    contract.status = "active"
    contract.save(update_fields=["status", "next_visit_date"])
    _recurring_active(contract, True)
    plan_visits(contract)


def cancel(contract):
    if contract.status in ("cancelled", "ended"):
        raise ValidationError(_("This contract is already closed."))
    contract.status, contract.next_visit_date = "cancelled", None
    contract.save(update_fields=["status", "next_visit_date"])
    _recurring_active(contract, False)
    now = timezone.now()
    ServiceCase.objects.filter(contract=contract, status="open", scheduled_at__gt=now).update(
        status="cancelled", closed_date=timezone.localdate())


def renew(contract, user, *, contract_value=None):
    """A new contract for the same length, starting the day after this one ends."""
    if contract.renewals.exclude(status="cancelled").exists():
        raise ValidationError(_("This contract was already renewed."))
    start = contract.end_date + timedelta(days=1)
    length = contract.end_date - contract.start_date
    end = start + length
    profile = contract.profile
    value = contract.contract_value if contract_value in (None, "") else Decimal(contract_value)
    return create_contract(
        contract.company, user, customer=contract.customer, title=contract.title, start_date=start, end_date=end,
        visit_every=contract.visit_every, preferred_time=contract.preferred_time, visit_minutes=contract.visit_minutes,
        staff=contract.staff, visit_task=contract.visit_task, contract_value=value, billing=contract.billing,
        site_name=profile.subject_name if profile else "", identifier=profile.identifier if profile else "",
        site_address=contract.site_address, notes=contract.notes, renewed_from=contract)


def expiring(company, days=30, today=None):
    today = today or timezone.localdate()
    return (ServiceContract.objects.for_company(company).filter(status__in=("active", "paused"),
                                                                end_date__lte=today + timedelta(days=days))
            .exclude(renewals__status__in=("active", "paused")).select_related("customer").order_by("end_date"))


def renewal_whatsapp(contract):
    from apps.sales.sharing import normalise_phone
    number = normalise_phone(contract.customer.phone, contract.company.country)
    if not number:
        return ""
    text = _("Hello %(name)s, your maintenance contract %(number)s (%(title)s) with %(shop)s ends on %(date)s. Shall we renew it for you?") % {  # noqa: E501
        "name": contract.customer.name, "number": contract.number,
                                               "title": contract.title, "shop": contract.company.name,
                                               "date": contract.end_date.strftime("%d %b %Y")}
    return f"https://wa.me/{number}?text={quote(text)}"


def run_daily(today=None):
    """Daily job: make the coming week's visits, close finished contracts, warn about ones ending soon."""
    from apps.notifications.rules import once
    from apps.notifications.services import notify
    today = today or timezone.localdate()
    counts = {"visits": 0, "ended": 0, "expiring": 0}
    for contract in ServiceContract._base_manager.filter(status="active").select_related("company"):
        if not contract.company.is_active:
            continue
        if contract.end_date < today:
            contract.status, contract.next_visit_date = "ended", None
            contract.save(update_fields=["status", "next_visit_date"])
            _recurring_active(contract, False)
            counts["ended"] += 1
            continue
        try:
            counts["visits"] += plan_visits(contract, today=today)
        except ValidationError:
            continue
        if contract.end_date <= today + timedelta(days=30) and not contract.renewals.exclude(status="cancelled").exists():
            if once(contract.company, f"amc-ending:{contract.pk}:{contract.end_date.isoformat()}"):
                notify(company=contract.company, notif_type="general",
                       title=_("Contract %(number)s ends on %(date)s") % {"number": contract.number,
                                                                          "date": contract.end_date.strftime("%d %b %Y")},
                       message=_("%(customer)s — %(title)s. Renew it from Service contracts.") % {
                           "customer": contract.customer.name, "title": contract.title})
                counts["expiring"] += 1
    return counts
