"""
Property management: buildings, units, tenancy contracts and monthly rent.

A unit can only have one active lease at a time. The monthly rent run bills
every lease that covers the month, once (RentCharge per lease and month).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from .common import invoice as make_invoice, money, service_product
from .education import month_bounds, month_key
from .models import Lease, RentalUnit, RentCharge


def unit_product(unit):
    product = service_product(unit.company, f"RENT-{unit.pk}", f"Rent · {unit.property.name} {unit.name}", unit.monthly_rent)
    if unit.product_id != product.pk:
        RentalUnit.objects.filter(pk=unit.pk).update(product=product)
        unit.product = product
    return product


def overlapping(unit, start, end, exclude=None):
    qs = Lease.objects.filter(unit=unit, status="active", start_date__lte=end, end_date__gte=start)
    return qs.exclude(pk=exclude.pk) if exclude else qs


@transaction.atomic
def create_lease(*, company, user, unit, tenant, start_date, end_date, monthly_rent, due_day=1, security_deposit=0,
                 notes="", bill_first_month=True):
    unit = RentalUnit.objects.select_for_update().select_related("property").get(pk=unit.pk, company=company)
    if end_date <= start_date:
        raise ValidationError("The lease must end after it starts.")
    rent = money(monthly_rent, "rent")
    if rent <= 0:
        raise ValidationError("Enter the monthly rent.")
    if not 1 <= int(due_day) <= 28:
        raise ValidationError("Rent due day must be between 1 and 28.")
    clash = overlapping(unit, start_date, end_date).select_related("tenant").first()
    if clash:
        raise ValidationError(f"{unit} is already leased to {clash.tenant.name} until {clash.end_date:%d %b %Y} ({clash.number}).")
    lease = Lease.objects.create(company=company, unit=unit, tenant=tenant, start_date=start_date, end_date=end_date,
                                 monthly_rent=rent, due_day=int(due_day), security_deposit=money(security_deposit, "deposit"),
                                 notes=notes, created_by=user)
    lease.number = f"LS-{lease.pk:05d}"
    lease.save(update_fields=["number"])
    if bill_first_month:
        bill(company=company, user=user, leases=[lease], key=month_key(start_date))
    return lease


def unpaid_charges(lease):
    return [c for c in lease.charges.select_related("invoice").order_by("period")
            if c.invoice_id and c.invoice.amount_paid < c.invoice.total]


@transaction.atomic
def receive_rent(lease, *, user, amount, method="cash", on=None):
    """Take a rent payment from the tenant and settle the oldest unpaid months first."""
    from .common import pay
    amount = money(amount, "payment")
    if amount <= 0:
        raise ValidationError("Enter the amount received.")
    open_charges = unpaid_charges(lease)
    due = sum((c.invoice.total - c.invoice.amount_paid for c in open_charges), Decimal("0"))
    if amount > due:
        raise ValidationError(f"The tenant owes {due}; the payment is more than that.")
    left, settled = amount, []
    for c in open_charges:
        if left <= 0:
            break
        part = min(left, c.invoice.total - c.invoice.amount_paid)
        pay(lease.company, user, c.invoice, part, method, on or timezone.localdate())
        left -= part
        settled.append(c.period)
    return settled


def rent_message(lease):
    """WhatsApp text to the tenant: what is unpaid, or a thank-you when nothing is."""
    from django.utils.translation import gettext as _
    open_charges = unpaid_charges(lease)
    name = lease.tenant.name
    if not open_charges:
        return _("Hi %(name)s, thank you! Your rent for %(unit)s is fully paid. – %(shop)s") % {
            "name": name, "unit": lease.unit, "shop": lease.company.name}
    due = sum((c.invoice.total - c.invoice.amount_paid for c in open_charges), Decimal("0"))
    return _("Hi %(name)s, a reminder from %(shop)s: rent for %(unit)s is due for %(months)s. "
             "Amount due: %(due)s. Please pay at the earliest. Thank you.") % {
        "name": name, "shop": lease.company.name, "unit": lease.unit,
        "months": ", ".join(month_label(c.period) for c in open_charges), "due": due}


def month_label(key):
    return month_bounds(key)[0].strftime("%b %Y")


@transaction.atomic
def renew_lease(lease, *, user, months=12, increase_percent=0):
    """A new lease for the same unit and tenant from the day after this one ends, rent raised by a percentage."""
    if lease.status != "active":
        raise ValidationError("Only an active lease can be renewed.")
    if Lease.objects.filter(unit=lease.unit, status="active", start_date__gt=lease.end_date).exists():
        raise ValidationError("This unit already has a lease after this one.")
    months = int(months)
    if not 1 <= months <= 120:
        raise ValidationError("Renew for 1 to 120 months.")
    start = lease.end_date + timedelta(days=1)
    y, m = divmod(start.month - 1 + months, 12)
    end = date(start.year + y, m + 1, 1) - timedelta(days=1) if start.day == 1 else \
        date(start.year + y, m + 1, min(start.day, 28)) - timedelta(days=1)
    rent = (lease.monthly_rent * (Decimal("100") + Decimal(str(increase_percent))) / Decimal("100")).quantize(Decimal("1"))
    new = Lease.objects.create(company=lease.company, unit=lease.unit, tenant=lease.tenant, start_date=start, end_date=end,
                               monthly_rent=rent, due_day=lease.due_day, security_deposit=lease.security_deposit,
                               notes=f"Renewal of {lease.number}", created_by=user)
    new.number = f"LS-{new.pk:05d}"
    new.save(update_fields=["number"])
    return new


def end_lease(lease, *, on, early=False):
    if lease.status != "active":
        raise ValidationError("This lease is already closed.")
    lease.status = "terminated" if early else "ended"
    lease.ended_on = on
    if early and on < lease.end_date:
        lease.end_date = on
    lease.save(update_fields=["status", "ended_on", "end_date"])
    return lease


def _due_date(lease, key):
    first, last = month_bounds(key)
    return min(first + timedelta(days=lease.due_day - 1), last)


def leases_for_month(company, key):
    first, last = month_bounds(key)
    leases = list(Lease.objects.for_company(company).filter(status="active", start_date__lte=last, end_date__gte=first)
                  .select_related("unit__property", "tenant"))
    billed = set(RentCharge.objects.filter(lease__in=leases, period=key).values_list("lease_id", flat=True))
    return [l for l in leases if l.pk not in billed]


@transaction.atomic
def bill(*, company, user, leases, key):
    invoices = []
    for lease in leases:
        if RentCharge.objects.filter(lease=lease, period=key).exists():
            continue
        due = max(_due_date(lease, key), lease.start_date)  # a lease starting after the due day isn't late on day one
        inv = make_invoice(company, user, lease.tenant, [(unit_product(lease.unit), Decimal("1"), lease.monthly_rent)],
                           date=month_bounds(key)[0])
        if inv.due_date != due:
            inv.due_date = due
            inv.save(update_fields=["due_date"])
        try:
            with transaction.atomic():
                RentCharge.objects.create(company=company, lease=lease, period=key, amount=lease.monthly_rent,
                                          due_date=due, invoice=inv)
        except IntegrityError:
            raise ValidationError("Rent for this month was just generated by someone else. Refresh and try again.")
        invoices.append(inv)
    return invoices


def generate_month(*, company, user, key):
    return bill(company=company, user=user, leases=leases_for_month(company, key), key=key)


def overdue(company, today=None):
    """Unpaid rent past its due date, with days late."""
    today = today or timezone.localdate()
    charges = (RentCharge.objects.for_company(company).filter(due_date__lt=today, invoice__amount_paid__lt=F("invoice__total"))
               .select_related("lease__tenant", "lease__unit__property", "invoice").order_by("due_date"))
    return [{"charge": c, "due": c.invoice.total - c.invoice.amount_paid, "days": (today - c.due_date).days} for c in charges]


def summary(company, today=None):
    today = today or timezone.localdate()
    units = RentalUnit.objects.for_company(company).filter(is_active=True)
    active = Lease.objects.for_company(company).filter(status="active", start_date__lte=today, end_date__gte=today)
    occupied_ids = set(active.values_list("unit_id", flat=True))
    key = month_key(today)
    charges = RentCharge.objects.for_company(company).filter(period=key).select_related("invoice")
    billed = charges.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    collected = sum((min(c.invoice.amount_paid, c.invoice.total) for c in charges if c.invoice_id), Decimal("0"))
    unit_count = units.count()
    return {
        "units": unit_count, "occupied": len(occupied_ids), "vacant": unit_count - len(occupied_ids),
        "occupancy": round(len(occupied_ids) * 100 / unit_count) if unit_count else 0,
        "rent_roll": active.aggregate(t=Sum("monthly_rent"))["t"] or Decimal("0"),
        "billed": billed, "collected": collected, "month": key,
        "occupied_ids": occupied_ids,
        "expiring": list(Lease.objects.for_company(company).filter(status="active", end_date__gte=today,
                                                                   end_date__lte=today + timedelta(days=60))
                         .select_related("tenant", "unit__property").order_by("end_date")),
        "not_billed": len(leases_for_month(company, key)),
    }
