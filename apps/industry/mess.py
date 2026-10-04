"""
Restaurant mess: people who pay a monthly package and eat breakfast / lunch / dinner every day.

- A member joins a plan (meals included + monthly fee). Joining mid-month bills only the days left.
- Each meal is ticked when served; the same meal can't be served twice a day, outside the plan, or on a
  mess-cut day.
- Mess cut (leave): days away. If the plan refunds per day, last month's mess-cut days come off this
  month's bill (only for leaves of at least plan.min_leave_days days).
- Monthly bills: one invoice per member and month (MessCharge makes the run safe to repeat); unpaid
  invoices show as dues and can be shared like any other invoice.
"""
import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from .common import invoice as make_invoice, service_product
from .models import MessCharge, MessLeave, MessMeal, MessMember, MessPlan

MEALS = ("breakfast", "lunch", "dinner")
CENT = Decimal("0.01")


def month_key(day):
    return f"{day.year:04d}-{day.month:02d}"


def month_bounds(key):
    year, month = (int(x) for x in key.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def previous_key(key):
    first, _ = month_bounds(key)
    return month_key(first - timedelta(days=1))


def plan_product(plan):
    product = service_product(plan.company, f"MESS-{plan.pk}", f"Mess – {plan.name}", plan.monthly_fee)
    if plan.product_id != product.pk:
        MessPlan.objects.filter(pk=plan.pk).update(product=product)
        plan.product = product
    return product


def next_number(company):
    last = MessMember.objects.for_company(company).count() + 1
    while MessMember.objects.for_company(company).filter(number=f"M-{last:03d}").exists():
        last += 1
    return f"M-{last:03d}"


# ------------------------------------------------------------------ members

@transaction.atomic
def join(*, company, user, plan, customer, start_date, monthly_fee=None, notes="", bill_now=True):
    if not plan.is_active:
        raise ValidationError(f"{plan.name} is closed.")
    if MessMember.objects.for_company(company).filter(customer=customer, status__in=["active", "paused"]).exists():
        raise ValidationError(f"{customer.name} is already a mess member.")
    member = MessMember.objects.create(company=company, number=next_number(company), customer=customer, plan=plan,
                                       monthly_fee=monthly_fee, start_date=start_date, notes=notes)
    if bill_now:
        bill(company=company, user=user, members=[member], key=month_key(start_date), on=start_date)
    return member


def set_status(member, status, *, on=None):
    if status not in dict(MessMember.STATUS):
        raise ValidationError("Unknown status.")
    member.status = status
    member.end_date = (on or timezone.localdate()) if status == "ended" else None
    member.save(update_fields=["status", "end_date"])
    return member


def add_leave(*, company, member, from_date, to_date, reason=""):
    if to_date < from_date:
        raise ValidationError("The last day can't be before the first day.")
    if (to_date - from_date).days > 120:
        raise ValidationError("A mess cut can be at most 120 days.")
    if MessLeave.objects.filter(member=member, from_date__lte=to_date, to_date__gte=from_date).exists():
        raise ValidationError("These days overlap another mess cut.")
    return MessLeave.objects.create(company=company, member=member, from_date=from_date, to_date=to_date, reason=reason[:150])


def on_leave(member, day):
    return MessLeave.objects.filter(member=member, from_date__lte=day, to_date__gte=day).exists()


# ------------------------------------------------------------------ meals

def serve(*, company, user, member, meal, day=None):
    day = day or timezone.localdate()
    if meal not in MEALS:
        raise ValidationError("Unknown meal.")
    if member.status != "active":
        raise ValidationError(f"{member.customer.name}'s mess is {member.get_status_display().lower()}.")
    if day < member.start_date or (member.end_date and day > member.end_date):
        raise ValidationError(f"{member.customer.name}'s mess isn't running on {day:%d %b}.")
    if not getattr(member.plan, meal):
        raise ValidationError(f"{meal.capitalize()} isn't part of the {member.plan.name} plan.")
    if on_leave(member, day):
        raise ValidationError(f"{member.customer.name} is on mess cut today.")
    try:
        with transaction.atomic():
            return MessMeal.objects.create(company=company, member=member, date=day, meal=meal, served_by=user)
    except IntegrityError:
        raise ValidationError(f"{meal.capitalize()} was already given to {member.customer.name} today.")


def undo(*, member, meal, day=None):
    MessMeal.objects.filter(member=member, meal=meal, date=day or timezone.localdate()).delete()


def running_on(company, day):
    return (MessMember.objects.for_company(company).filter(status="active", start_date__lte=day)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=day)))


def today(company, day=None):
    """Kitchen count: per meal how many members should eat today and how many have been served."""
    day = day or timezone.localdate()
    members = running_on(company, day).select_related("plan")
    away = set(MessLeave.objects.for_company(company).filter(from_date__lte=day, to_date__gte=day)
               .values_list("member_id", flat=True))
    served = {}
    for row in MessMeal.objects.for_company(company).filter(date=day).values("meal").annotate(n=Count("id")):
        served[row["meal"]] = row["n"]
    out = []
    for meal in MEALS:
        expected = sum(1 for m in members if getattr(m.plan, meal) and m.pk not in away)
        out.append({"meal": meal, "expected": expected, "served": served.get(meal, 0),
                    "left": max(expected - served.get(meal, 0), 0)})
    return {"day": day, "meals": out, "away": len(away & {m.pk for m in members}), "members": len(members)}


def served_today(company, member_ids, day=None):
    day = day or timezone.localdate()
    out = {}
    for member_id, meal in MessMeal.objects.for_company(company).filter(date=day, member_id__in=member_ids).values_list("member_id", "meal"):
        out.setdefault(member_id, set()).add(meal)
    return out


# ------------------------------------------------------------------ billing

def _days(first, last):
    return (last - first).days + 1


def leave_days(member, key):
    """Mess-cut days inside that month, counting only leaves long enough for the plan's refund."""
    first, last = month_bounds(key)
    total = 0
    for leave in member.leaves.filter(from_date__lte=last, to_date__gte=first):
        if leave.days < member.plan.min_leave_days:
            continue
        total += _days(max(leave.from_date, first), min(leave.to_date, last))
    return total


def amount_for(member, key):
    """(fee for the month, refund for last month's mess cut, mess-cut days)."""
    first, last = month_bounds(key)
    start = max(member.start_date, first)
    end = min(member.end_date or last, last)
    if end < start:
        return Decimal("0"), Decimal("0"), 0
    fee = Decimal(str(member.fee))
    if start != first or end != last:  # joined or left during the month: only the days in it
        fee = (fee * _days(start, end) / _days(first, last)).quantize(CENT, rounding=ROUND_HALF_UP)
    per_day = Decimal(str(member.plan.leave_refund_per_day or 0))
    days = leave_days(member, previous_key(key)) if per_day > 0 else 0
    refund = min((per_day * days).quantize(CENT), fee)
    return fee, refund, days


def due_for_month(company, key):
    first, last = month_bounds(key)
    members = (MessMember.objects.for_company(company).filter(status__in=["active", "ended"], start_date__lte=last)
               .filter(Q(end_date__isnull=True) | Q(end_date__gte=first)).select_related("plan", "customer"))
    billed = set(MessCharge.objects.for_company(company).filter(period=key).values_list("member_id", flat=True))
    return [m for m in members if m.pk not in billed]


@transaction.atomic
def bill(*, company, user, members, key, on=None):
    """One invoice per member for the month. Already-billed members are skipped. Returns the invoices."""
    billed = set(MessCharge.objects.filter(member__in=members, period=key).values_list("member_id", flat=True))
    invoices = []
    first, _ = month_bounds(key)
    for member in members:
        if member.pk in billed:
            continue
        fee, refund, days = amount_for(member, key)
        price = fee - refund
        if fee <= 0:
            continue
        inv = None
        if price > 0:
            inv = make_invoice(company, user, member.customer, [(plan_product(member.plan), Decimal("1"), price)],
                               date=on or first)
        try:
            with transaction.atomic():
                MessCharge.objects.create(company=company, member=member, period=key, amount=price, leave_days=days,
                                          refund=refund, invoice=inv)
        except IntegrityError:
            raise ValidationError("This month was just billed by someone else. Refresh and try again.")
        if inv:
            invoices.append(inv)
    return invoices


def generate_month(*, company, user, key, on=None):
    return bill(company=company, user=user, members=due_for_month(company, key), key=key, on=on)


def dues(company):
    """Unpaid mess invoices per member, biggest first."""
    from apps.sales.models import SalesInvoice
    charges = (MessCharge.objects.for_company(company).exclude(invoice=None)
               .filter(invoice__amount_paid__lt=F("invoice__total")).select_related("member__customer", "invoice"))
    rows = {}
    for charge in charges:
        row = rows.setdefault(charge.member_id, {"member": charge.member, "invoices": [], "due": Decimal("0")})
        row["invoices"].append(charge.invoice)
        row["due"] += charge.invoice.total - charge.invoice.amount_paid
    return sorted(rows.values(), key=lambda r: -r["due"])


def month_grid(member, key):
    """Calendar rows for a member's month: each day with the meals served and whether it was a mess-cut day."""
    first, last = month_bounds(key)
    served = {}
    for day, meal in member.meals.filter(date__gte=first, date__lte=last).values_list("date", "meal"):
        served.setdefault(day, set()).add(meal)
    leaves = list(member.leaves.filter(from_date__lte=last, to_date__gte=first))
    days = []
    day = first
    while day <= last:
        days.append({"day": day, "meals": served.get(day, set()),
                     "leave": any(l.from_date <= day <= l.to_date for l in leaves)})
        day += timedelta(days=1)
    return days
