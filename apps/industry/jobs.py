"""Job cards and appointments for service businesses (clinics, garages, repair shops, laundries, AC service …).

    booked / walk-in (open) ─▶ in progress ─▶ (waiting for parts / approval) ─▶ ready ─▶ completed (billed)
                                                                                    └▶ cancelled

A job has parts and labour lines; "Bill" turns them into one invoice (parts come out of stock) and,
when paid there and then, records the payment. Each staff member can get a private phone page with
their jobs, and each job has a status link for the customer.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.verticals.saloon.models import ServiceCase, ServiceCaseLine, ServiceClientProfile, TechnicianLink

OPEN = ("open", "in_progress", "waiting", "ready")
LABOUR_SKU = "JOB-SERVICE"
PAY_METHODS = ("cash", "card", "bank")


def _money(value, default="0"):
    try:
        amount = Decimal(str(value if value not in (None, "") else default).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(_("Enter a valid amount."))
    if amount < 0 or amount > Decimal("10000000"):
        raise ValidationError(_("Enter a valid amount."))
    return amount


def profile_type(company):
    from apps.modules.catalog import business_profile
    return business_profile(company.business_type.code if company.business_type_id else "").get("profile_type", "person")


def profile_for(company, customer, subject_name="", identifier=""):
    """The record the work is about (the patient, the car, the laptop …); re-used when it already exists."""
    subject_name = (subject_name or "").strip()[:200] or customer.name
    identifier = (identifier or "").strip()[:100]
    qs = ServiceClientProfile.objects.for_company(company).filter(customer=customer, is_active=True)
    found = (qs.filter(identifier__iexact=identifier).first() if identifier else None) or \
        qs.filter(subject_name__iexact=subject_name).first()
    if found:
        return found
    return ServiceClientProfile.objects.create(company=company, customer=customer, profile_type=profile_type(company),
                                               subject_name=subject_name, identifier=identifier,
                                               reference_code=next_reference(company))


def next_reference(company):
    """Record numbers are unique per business, so a blank one can only be used once — give each its own."""
    from apps.tenants.services import next_counter_value
    while True:
        code = f"R-{next_counter_value(company, 'service_profile'):05d}"
        if not ServiceClientProfile.objects.for_company(company).filter(reference_code=code).exists():
            return code


def _number(company):
    from apps.tenants.services import next_counter_value
    return f"JOB-{next_counter_value(company, 'service_job'):05d}"


def clashes(company, staff, start, minutes, exclude=None):
    """Other appointments of the same staff member that overlap [start, start + minutes)."""
    if not staff or not start:
        return []
    end = start + timedelta(minutes=minutes or 30)
    qs = (ServiceCase.objects.for_company(company).filter(assigned_staff=staff, status__in=OPEN,
                                                          scheduled_at__lt=end, scheduled_at__gte=start - timedelta(hours=12))
          .exclude(pk=getattr(exclude, "pk", None)))
    return [c for c in qs if c.scheduled_at + timedelta(minutes=c.duration_minutes or 30) > start]


@transaction.atomic
def create_job(company, *, customer, title, subject_name="", identifier="", staff=None, scheduled_at=None,
               duration=30, ready_by=None, description="", priority="normal", case_type=""):
    title = (title or "").strip()[:200]
    if len(title) < 2:
        raise ValidationError(_("Say what the job is."))
    if staff is not None and staff.company_id != company.id:
        raise ValidationError(_("Choose your own staff member."))
    profile = profile_for(company, customer, subject_name, identifier)
    opened = timezone.localtime(scheduled_at).date() if scheduled_at else timezone.localdate()
    return ServiceCase.objects.create(
        company=company, profile=profile, title=title, description=(description or "")[:5000],
        case_type=(case_type or "")[:100], assigned_staff=staff, status="open", opened_date=opened,
        scheduled_at=scheduled_at, duration_minutes=max(5, min(int(duration or 30), 24 * 60)), ready_by=ready_by,
        due_date=timezone.localtime(ready_by).date() if ready_by else None,
        priority=priority if priority in ("normal", "urgent") else "normal", number=_number(company))


def ensure_number(job):
    if not job.number:
        job.number = _number(job.company)
        job.save(update_fields=["number"])
    return job


def _editable(job):
    if job.status in ("completed", "cancelled") or job.invoice_id:
        raise ValidationError(_("This job is closed."))


def add_line(job, *, kind="labour", product=None, description="", quantity=1, unit_price=None):
    _editable(job)
    if product is not None and product.company_id != job.company_id:
        raise ValidationError(_("Choose your own item."))
    qty = _money(quantity, "1")
    if qty <= 0:
        raise ValidationError(_("Quantity must be more than 0."))
    if unit_price not in (None, ""):
        price = _money(unit_price)
    else:
        price = product.selling_price if product is not None else Decimal("0")
    description = (description or "").strip()[:200] or (product.name if product is not None else "")
    if not description:
        raise ValidationError(_("Describe the work or choose an item."))
    if kind not in ("part", "labour"):
        kind = "part" if product is not None and product.is_stock_tracked else "labour"
    return ServiceCaseLine.objects.create(company=job.company, case=job, kind=kind, product=product,
                                          description=description, quantity=qty, unit_price=price)


def remove_line(job, line_id):
    _editable(job)
    job.lines.filter(pk=line_id).delete()


def total(job):
    return sum((l.total for l in job.lines.all()), Decimal("0"))


def set_status(job, status):
    if status not in ("open", "in_progress", "waiting", "ready", "cancelled"):
        raise ValidationError(_("Unknown status."))
    _editable(job)
    now = timezone.now()
    job.status = status
    fields = ["status"]
    if status == "in_progress" and not job.started_at:
        job.started_at = now
        fields.append("started_at")
    if status == "ready":
        job.finished_at = now
        fields.append("finished_at")
    if status == "cancelled":
        job.closed_date = timezone.localdate()
        fields.append("closed_date")
    job.save(update_fields=fields)
    return job


def close_without_bill(job):
    """Free work or work already paid elsewhere (package, warranty)."""
    _editable(job)
    job.status, job.closed_date = "completed", timezone.localdate()
    job.finished_at = job.finished_at or timezone.now()
    job.save(update_fields=["status", "closed_date", "finished_at"])
    return job


def _warehouse(company):
    from apps.inventory.models import Warehouse
    qs = Warehouse.objects.for_company(company).filter(is_active=True)
    return qs.filter(is_default=True).first() or qs.first() or Warehouse.objects.create(
        company=company, name="Main Branch", is_active=True, is_default=True)


@transaction.atomic
def bill(job, user, *, method="", warehouse=None, discount=Decimal("0")):
    """Parts and labour → one invoice. ``method`` cash/card/bank also records the payment; empty = on account."""
    from apps.industry.common import service_product
    from apps.sales.services import create_invoice, record_customer_payment
    job = ServiceCase.objects.select_for_update().get(pk=job.pk)
    _editable(job)
    lines = list(job.lines.select_related("product"))
    if not lines:
        raise ValidationError(_("Add the parts and work done first."))
    company = job.company
    labour = None
    invoice_lines = []
    for line in lines:
        product = line.product
        if product is None:
            labour = labour or service_product(company, LABOUR_SKU, "Service charge")
            product = labour
        invoice_lines.append({"product": product, "quantity": line.quantity, "unit_price": line.unit_price})
    discount = _money(discount)
    if discount > total(job):
        raise ValidationError(_("The discount is more than the bill."))
    customer = job.profile.customer
    today = timezone.localdate()
    invoice = create_invoice(company=company, user=user, customer=customer, date=today,
                             warehouse=warehouse or _warehouse(company), lines=invoice_lines, discount_amount=discount,
                             discount_reason=f"{job.number} discount" if discount else "",
                             discount_approved_by=user if discount else None)
    balance = invoice.transaction_total
    advance_id = (job.record or {}).get("advance_payment_id")
    if advance_id:
        # the advance paid when the order was taken now counts against this bill
        from apps.sales.models import CustomerPayment
        paid = CustomerPayment.objects.filter(company=company, id=advance_id, invoice__isnull=True).first()
        if paid is not None:
            used = min(paid.amount, invoice.total)
            paid.invoice = invoice
            paid.save(update_fields=["invoice"])
            invoice.amount_paid += used
            invoice.transaction_amount_paid += used
            invoice.status = "paid" if invoice.transaction_amount_paid >= invoice.transaction_total else "partial"
            invoice.save(update_fields=["amount_paid", "transaction_amount_paid", "status"])
            balance = max(invoice.transaction_total - invoice.transaction_amount_paid, Decimal("0"))
    if method in PAY_METHODS and balance > 0:
        record_customer_payment(company=company, user=user, customer=customer, invoice=invoice,
                                amount=balance, date=today, method=method)
    job.invoice, job.status, job.closed_date = invoice, "completed", today
    job.finished_at = job.finished_at or timezone.now()
    job.save(update_fields=["invoice", "status", "closed_date", "finished_at"])
    return invoice


def status_url(request_or_base, job):
    from django.urls import reverse
    path = reverse("webapp:job_status_page", args=[job.token])
    return request_or_base.build_absolute_uri(path) if hasattr(request_or_base, "build_absolute_uri") else \
        f"{(request_or_base or '').rstrip('/')}{path}"


def customer_message(job, link=""):
    """The WhatsApp text for the customer at the job's current step."""
    company = job.company
    who = job.profile.customer.name
    what = f"{job.title}" + (f" ({job.profile.subject_name})" if job.profile.subject_name != who else "")
    lines = [_("Hello %(name)s,") % {"name": who}]
    if job.status == "open" and job.scheduled_at:
        when = timezone.localtime(job.scheduled_at)
        lines.append(_("Your appointment at %(shop)s is booked: %(what)s on %(when)s.") % {
            "shop": company.name, "what": what, "when": when.strftime("%d %b %Y %H:%M")})
    elif job.status == "ready":
        lines.append(_("Good news — %(what)s is ready at %(shop)s.") % {"what": what, "shop": company.name})
        amount = total(job)
        if amount:
            lines.append(_("Amount: %(amount)s") % {"amount": f"{company.default_currency} {amount:.2f}"})
    elif job.status == "waiting":
        lines.append(_("%(what)s is waiting for parts / your approval. We will update you.") % {"what": what})
    elif job.status == "completed":
        lines.append(_("Thank you for choosing %(shop)s. Job %(number)s is complete.") % {"shop": company.name, "number": job.number})
    else:
        lines.append(_("We are working on %(what)s (job %(number)s).") % {"what": what, "number": job.number})
    if link:
        lines.append(_("Status: %(url)s") % {"url": link})
    return "\n".join(lines)


def whatsapp_url(job, link=""):
    from apps.sales.sharing import normalise_phone
    number = normalise_phone(job.profile.customer.phone, job.company.country)
    return f"https://wa.me/{number}?text={quote(customer_message(job, link))}" if number else ""


def technician_link(employee):
    link, _created = TechnicianLink.objects.get_or_create(company=employee.company, employee=employee)
    return link


def technician_jobs(employee):
    """Open jobs of this staff member, today's appointments first."""
    today = timezone.localdate()
    qs = (ServiceCase.objects.for_company(employee.company).filter(assigned_staff=employee)
          .select_related("profile", "profile__customer").prefetch_related("lines"))
    open_jobs = list(qs.filter(status__in=OPEN))
    open_jobs.sort(key=lambda j: (0 if j.scheduled_at and timezone.localtime(j.scheduled_at).date() == today else 1,
                                  j.scheduled_at or timezone.now() + timedelta(days=3650), j.pk))
    done_today = list(qs.filter(status="completed", closed_date=today))
    return open_jobs, done_today


def day_plan(company, day):
    """Appointments of one day per staff member (and unassigned), in time order."""
    from apps.employees.models import Employee
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = start + timedelta(days=1)
    jobs = list(ServiceCase.objects.for_company(company).filter(scheduled_at__gte=start, scheduled_at__lt=end)
                .exclude(status="cancelled").select_related("profile", "profile__customer", "assigned_staff")
                .order_by("scheduled_at"))
    staff = list(Employee.objects.for_company(company).filter(is_active=True).order_by("name"))
    columns = [{"staff": s, "jobs": [j for j in jobs if j.assigned_staff_id == s.id]} for s in staff]
    unassigned = [j for j in jobs if j.assigned_staff_id is None or j.assigned_staff_id not in {s.id for s in staff}]
    if unassigned:
        columns.insert(0, {"staff": None, "jobs": unassigned})
    for col in columns:
        for j in col["jobs"]:
            j.ends_at = j.scheduled_at + timedelta(minutes=j.duration_minutes or 30)
    return columns, len(jobs)


def overdue(job):
    return job.status in OPEN and job.ready_by is not None and job.ready_by < timezone.now()
