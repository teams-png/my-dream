"""
Restaurant mess: people who pay a monthly package and eat breakfast / lunch / dinner every day.

- A member joins a plan (meals included + monthly fee). Joining mid-month bills only the days left.
- Each meal is ticked when served; the same meal can't be served twice a day, outside the plan, or on a
  mess-cut day.
- Mess cut (leave): days away. If the plan refunds per day, last month's mess-cut days come off this
  month's bill (only for leaves of at least plan.min_leave_days days).
- Monthly bills: one invoice per member and month (MessCharge makes the run safe to repeat); unpaid
  invoices show as dues and can be shared like any other invoice.
- Extras (chicken, egg, juice…) given on top of the plan wait until the member's next mess bill and are
  added to it as their own lines; members who are paused or have left get a bill for just their extras.
- Each plan has a weekly menu (weekday x meal), shown on today's page and shared on WhatsApp or printed.
- A member can have some meals delivered; served meals record whether they were eaten here or delivered.
"""
import calendar
import hashlib
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from .common import invoice as make_invoice, service_product
from .models import MessCharge, MessExtra, MessExtraItem, MessLeave, MessMeal, MessMember, MessMenu, MessPlan

MEALS = ("breakfast", "lunch", "dinner")
MEAL_ICON = {"breakfast": "☕", "lunch": "🍛", "dinner": "🌙"}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_EXTRA_QTY = Decimal("50")
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
def join(*, company, user, plan, customer, start_date, monthly_fee=None, notes="", bill_now=True,
         delivery_meals=(), delivery_address=""):
    if not plan.is_active:
        raise ValidationError(f"{plan.name} is closed.")
    if MessMember.objects.for_company(company).filter(customer=customer, status__in=["active", "paused"]).exists():
        raise ValidationError(f"{customer.name} is already a mess member.")
    member = MessMember.objects.create(company=company, number=next_number(company), customer=customer, plan=plan,
                                       monthly_fee=monthly_fee, start_date=start_date, notes=notes,
                                       delivery_meals=delivery_value(delivery_meals),
                                       delivery_address=(delivery_address or "")[:255])
    if bill_now:
        bill(company=company, user=user, members=[member], key=month_key(start_date), on=start_date)
    return member


def delivery_value(meals):
    return ",".join(m for m in MEALS if m in set(meals or ()))


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

def serve(*, company, user, member, meal, day=None, mode=None):
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
            if mode not in dict(MessMeal.MODES):
                mode = "delivery" if member.delivers(meal) else "dine_in"
            return MessMeal.objects.create(company=company, member=member, date=day, meal=meal, served_by=user, mode=mode)
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
        eating = [m for m in members if getattr(m.plan, meal) and m.pk not in away]
        expected = len(eating)
        out.append({"meal": meal, "expected": expected, "served": served.get(meal, 0),
                    "left": max(expected - served.get(meal, 0), 0),
                    "delivery": sum(1 for m in eating if m.delivers(meal)),
                    "dine_in": sum(1 for m in eating if not m.delivers(meal))})
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
    """One invoice per member for the month, with the extras given so far. Already-billed members are
    skipped. Returns the invoices."""
    billed = set(MessCharge.objects.filter(member__in=members, period=key).values_list("member_id", flat=True))
    invoices = []
    first, _ = month_bounds(key)
    upto = max(on or timezone.localdate(), first)
    for member in members:
        if member.pk in billed:
            continue
        fee, refund, days = amount_for(member, key)
        price = fee - refund
        if fee <= 0:
            continue
        extras = list(pending_extras(member, upto).select_for_update())
        extra_total = sum((e.total for e in extras), Decimal("0"))
        lines = [(plan_product(member.plan), Decimal("1"), price)] if price > 0 else []
        lines += extra_lines(company, extras)
        inv = make_invoice(company, user, member.customer, lines, date=on or first) if lines else None
        try:
            with transaction.atomic():
                MessCharge.objects.create(company=company, member=member, period=key, amount=price + extra_total,
                                          leave_days=days, refund=refund, extras=extra_total, invoice=inv)
        except IntegrityError:
            raise ValidationError("This month was just billed by someone else. Refresh and try again.")
        if extras:
            MessExtra.objects.filter(pk__in=[e.pk for e in extras]).update(invoice=inv)
        if inv:
            invoices.append(inv)
    return invoices


def generate_month(*, company, user, key, on=None):
    invoices = bill(company=company, user=user, members=due_for_month(company, key), key=key, on=on)
    # paused or finished members don't get a monthly bill, so their extras are billed on their own
    upto = on or timezone.localdate()
    waiting = (MessMember.objects.for_company(company).exclude(status="active")
               .filter(extras__invoice__isnull=True, extras__date__lte=upto).distinct())
    for member in waiting:
        inv = bill_extras(company=company, user=user, member=member, upto=upto)
        if inv:
            invoices.append(inv)
    return invoices


# ------------------------------------------------------------------ extras

def extra_product(company, name, price, item=None):
    if item is not None:
        return service_product(company, f"MESS-EXTRA-{item.pk}", f"Mess extra – {item.name}", item.price)
    digest = hashlib.sha1(name.strip().lower().encode()).hexdigest()[:10]
    return service_product(company, f"MESS-X-{digest}", f"Mess extra – {name.strip()}", price)


def add_extra(*, company, user, member, item=None, name="", quantity=1, unit_price=None, day=None, meal=""):
    """Give a member something on top of the plan; it goes on their next mess bill."""
    if member.status == "ended":
        raise ValidationError(f"{member.customer.name}'s mess has ended.")
    if item is not None:
        if item.company_id != company.pk:
            raise ValidationError("Unknown extra.")
        name = item.name
        unit_price = item.price if unit_price is None else unit_price
    name = (name or "").strip()
    if not name:
        raise ValidationError("Choose an extra or type its name.")
    try:
        quantity = Decimal(str(quantity))
        unit_price = Decimal(str(unit_price))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Quantity and price must be numbers.")
    if quantity <= 0 or quantity > MAX_EXTRA_QTY:
        raise ValidationError(f"Quantity must be between 1 and {MAX_EXTRA_QTY:.0f}.")
    if unit_price < 0:
        raise ValidationError("The price can't be negative.")
    if meal and meal not in MEALS:
        meal = ""
    return MessExtra.objects.create(company=company, member=member, item=item, date=day or timezone.localdate(),
                                    meal=meal, name=name[:120], quantity=quantity, unit_price=unit_price.quantize(CENT),
                                    added_by=user)


def remove_extra(extra):
    if extra.invoice_id:
        raise ValidationError("This extra is already on a bill.")
    extra.delete()


def pending_extras(member, upto=None):
    qs = member.extras.filter(invoice__isnull=True)
    return qs.filter(date__lte=upto) if upto else qs


def pending_total(member, upto=None):
    return sum((e.total for e in pending_extras(member, upto)), Decimal("0"))


def extra_lines(company, extras):
    """Invoice lines: the same extra at the same price becomes one line with the total quantity."""
    grouped = {}
    for e in extras:
        key = (e.item_id or e.name.strip().lower(), e.unit_price)
        row = grouped.setdefault(key, {"extra": e, "qty": Decimal("0")})
        row["qty"] += e.quantity
    return [(extra_product(company, r["extra"].name, r["extra"].unit_price, r["extra"].item), r["qty"], price)
            for (_, price), r in grouped.items()]


@transaction.atomic
def bill_extras(*, company, user, member, upto=None):
    """A bill for just the extras not billed yet (e.g. when a member leaves mid-month)."""
    extras = list(pending_extras(member, upto).select_for_update())
    if not extras:
        return None
    inv = make_invoice(company, user, member.customer, extra_lines(company, extras), date=upto or timezone.localdate())
    MessExtra.objects.filter(pk__in=[e.pk for e in extras]).update(invoice=inv)
    return inv


# ------------------------------------------------------------------ weekly menu

def menu_grid(plan):
    """{(weekday, meal): items} for a plan."""
    return {(m.weekday, m.meal): m.items for m in plan.menu.all()}


@transaction.atomic
def save_menu(plan, entries):
    """entries: {(weekday, meal): text}; empty text clears that slot. Meals outside the plan are ignored."""
    for (weekday, meal), text in entries.items():
        if meal not in plan.meals() or not 0 <= weekday <= 6:
            continue
        text = " ".join((text or "").split())[:255]
        if text:
            MessMenu.objects.update_or_create(company=plan.company, plan=plan, weekday=weekday, meal=meal,
                                              defaults={"items": text})
        else:
            MessMenu.objects.filter(plan=plan, weekday=weekday, meal=meal).delete()


def menu_for_day(company, day=None):
    """Today's menu per active plan: [{"plan": plan, "meals": [(meal, items)]}] (plans without a menu are left out)."""
    day = day or timezone.localdate()
    rows = {}
    for m in MessMenu.objects.for_company(company).filter(weekday=day.weekday(), plan__is_active=True).select_related("plan"):
        rows.setdefault(m.plan_id, {"plan": m.plan, "items": {}})["items"][m.meal] = m.items
    out = []
    for row in sorted(rows.values(), key=lambda r: r["plan"].name):
        out.append({"plan": row["plan"], "meals": [(meal, row["items"][meal]) for meal in MEALS if meal in row["items"]]})
    return out


def menu_text(plan, *, company_name="", day=None):
    """The menu as a WhatsApp message: the whole week, or one day when `day` is given."""
    grid = menu_grid(plan)
    days = [day.weekday()] if day else range(7)
    lines = [f"🍱 {company_name} – {plan.name}".strip(" –"), ""]
    if day:
        lines[0] += f" · {day:%A %d %b}"
    for wd in days:
        meals = [(meal, grid[(wd, meal)]) for meal in MEALS if (wd, meal) in grid]
        if not meals:
            continue
        if not day:
            lines.append(f"*{WEEKDAYS[wd]}*")
        lines += [f"{MEAL_ICON[meal]} {meal.capitalize()}: {items}" for meal, items in meals]
        if not day:
            lines.append("")
    return "\n".join(lines).strip()


# ------------------------------------------------------------------ delivery

def delivery_list(company, meal, day=None):
    """Members to deliver this meal to today, with address and whether it has gone out."""
    day = day or timezone.localdate()
    if meal not in MEALS:
        return []
    away = set(MessLeave.objects.for_company(company).filter(from_date__lte=day, to_date__gte=day)
               .values_list("member_id", flat=True))
    done = set(MessMeal.objects.for_company(company).filter(date=day, meal=meal).values_list("member_id", flat=True))
    out = []
    for m in running_on(company, day).select_related("customer", "plan").order_by("number"):
        if getattr(m.plan, meal) and m.delivers(meal) and m.pk not in away:
            out.append({"m": m, "address": m.delivery_address or m.customer.address or "", "done": m.pk in done})
    return out


def dues(company):
    """Unpaid mess invoices (monthly bills and extras-only bills) per member, biggest first."""
    owner = dict(MessCharge.objects.for_company(company).exclude(invoice=None).values_list("invoice_id", "member_id"))
    owner.update(MessExtra.objects.for_company(company).exclude(invoice=None).values_list("invoice_id", "member_id"))
    from apps.sales.models import SalesInvoice
    unpaid = SalesInvoice.objects.filter(company=company, pk__in=owner, amount_paid__lt=F("total")).order_by("date")
    members = {m.pk: m for m in MessMember.objects.for_company(company).filter(pk__in=set(owner.values()))
               .select_related("customer")}
    rows = {}
    for inv in unpaid:
        member_id = owner[inv.pk]
        row = rows.setdefault(member_id, {"member": members[member_id], "invoices": [], "due": Decimal("0")})
        row["invoices"].append(inv)
        row["due"] += inv.total - inv.amount_paid
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
