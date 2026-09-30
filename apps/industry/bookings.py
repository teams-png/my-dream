"""
Bookings for rooms, vehicles, equipment, halls and desks.

A resource can't be booked twice for overlapping times. Check-out turns the
stay into an invoice: billed units x rate (late returns are charged up to
the actual check-out time), plus extras, minus discount, with the advance
and the amount paid now recorded against it.
"""
import math
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .common import invoice as make_invoice, money, pay, service_product
from .models import BookableResource, Booking

GRACE = timedelta(minutes=30)  # returns within the grace period aren't charged extra


def billable_units(rate_unit, start, end):
    """How many units of the rate a stay from start to end costs (at least 1)."""
    seconds = max((end - start).total_seconds(), 0)
    if rate_unit == "hour":
        units = math.ceil(max(seconds - GRACE.total_seconds(), 0) / 3600) or 1
    elif rate_unit == "day":
        units = math.ceil(max(seconds - GRACE.total_seconds(), 0) / 86400) or 1
    elif rate_unit == "night":
        units = max((timezone.localtime(end).date() - timezone.localtime(start).date()).days, 1)
    elif rate_unit == "month":
        units = math.ceil(seconds / (30 * 86400)) or 1
    else:  # per booking / event
        units = 1
    return Decimal(units)


def conflicts(resource, start, end, exclude=None):
    qs = Booking.objects.filter(company=resource.company, resource=resource, status__in=Booking.ACTIVE,
                                start__lt=end, end__gt=start)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def _check_times(start, end):
    if not start or not end:
        raise ValidationError("Choose the start and end.")
    if end <= start:
        raise ValidationError("The end must be after the start.")
    if end - start > timedelta(days=400):
        raise ValidationError("A booking can be at most 400 days.")


def resource_product(resource):
    product = service_product(resource.company, f"RES-{resource.pk}", resource.name, resource.rate)
    if resource.product_id != product.pk:
        BookableResource.objects.filter(pk=resource.pk).update(product=product)
        resource.product = product
    return product


@transaction.atomic
def create_booking(*, company, user, resource, customer, start, end, guests=1, advance=0, advance_method="cash",
                   security_deposit=0, notes=""):
    _check_times(start, end)
    resource = BookableResource.objects.select_for_update().get(pk=resource.pk, company=company)
    if not resource.is_active:
        raise ValidationError(f"{resource.name} is not available for booking.")
    clash = conflicts(resource, start, end).first()
    if clash:
        raise ValidationError(
            f"{resource.name} is already booked from {timezone.localtime(clash.start):%d %b %H:%M} "
            f"to {timezone.localtime(clash.end):%d %b %H:%M} ({clash.number}).")
    if resource.capacity and guests and guests > resource.capacity:
        raise ValidationError(f"{resource.name} takes at most {resource.capacity}.")
    booking = Booking.objects.create(
        company=company, resource=resource, customer=customer, start=start, end=end, guests=guests or 1,
        rate=resource.rate, rate_unit=resource.rate_unit, advance=money(advance, "advance"),
        advance_method=advance_method, advance_date=timezone.localdate() if money(advance) else None,
        security_deposit=money(security_deposit, "deposit"), notes=notes, created_by=user,
    )
    booking.number = f"BK-{booking.pk:05d}"
    booking.save(update_fields=["number"])
    return booking


@transaction.atomic
def reschedule(booking, *, resource, start, end, guests=None):
    _check_times(start, end)
    if booking.status not in Booking.ACTIVE:
        raise ValidationError("Only upcoming or current bookings can be changed.")
    resource = BookableResource.objects.select_for_update().get(pk=resource.pk, company=booking.company)
    clash = conflicts(resource, start, end, exclude=booking).first()
    if clash:
        raise ValidationError(f"{resource.name} is already booked then ({clash.number}).")
    if booking.resource_id != resource.pk:
        booking.rate, booking.rate_unit = resource.rate, resource.rate_unit
    booking.resource, booking.start, booking.end = resource, start, end
    if guests:
        booking.guests = guests
    booking.save()
    return booking


def check_in(booking):
    if booking.status != "reserved":
        raise ValidationError("Only a reserved booking can be checked in.")
    booking.status, booking.checked_in_at = "checked_in", timezone.now()
    booking.save(update_fields=["status", "checked_in_at"])
    return booking


def cancel(booking, status="cancelled"):
    if booking.status != "reserved":
        raise ValidationError("Only a reserved booking can be cancelled.")
    booking.status = status
    booking.save(update_fields=["status"])
    return booking


def charge_preview(booking, until=None):
    """What check-out would bill right now."""
    end = booking.end
    until = until or timezone.now()
    if booking.status == "checked_in" and until > booking.end + GRACE:
        end = until  # late return
    units = billable_units(booking.rate_unit, booking.start, end)
    rent = (units * booking.rate).quantize(Decimal("0.01"))
    return {"units": units, "rent": rent, "late": end != booking.end, "billed_until": end}


@transaction.atomic
def check_out(booking, *, user, extras=0, extras_note="", discount=0, paid_now=0, method="cash", when=None):
    booking = Booking.objects.select_for_update().select_related("resource", "customer").get(pk=booking.pk)
    if booking.status not in ("reserved", "checked_in"):
        raise ValidationError("This booking is already closed.")
    when = when or timezone.now()
    preview = charge_preview(booking, when)
    extras, discount, paid_now = money(extras, "extras"), money(discount, "discount"), money(paid_now, "payment")
    product = resource_product(booking.resource)
    lines = [(product, preview["units"], booking.rate)]
    if extras:
        extra_product = service_product(booking.company, "BOOKING-EXTRAS", extras_note or "Extras / services")
        lines.append((extra_product, Decimal("1"), extras))
    inv = make_invoice(booking.company, user, booking.customer, lines, date=timezone.localdate(when),
                       discount=discount, discount_reason=f"Booking {booking.number}")
    if booking.advance + paid_now > inv.total:
        raise ValidationError(f"Payments ({booking.advance + paid_now}) are more than the bill ({inv.total}).")
    pay(booking.company, user, inv, booking.advance, booking.advance_method, booking.advance_date or timezone.localdate(when))
    pay(booking.company, user, inv, paid_now, method, timezone.localdate(when))
    booking.status = "completed"
    booking.checked_out_at = when
    booking.checked_in_at = booking.checked_in_at or booking.start
    booking.extras, booking.extras_note, booking.discount, booking.invoice = extras, extras_note, discount, inv
    booking.save()
    return booking


def board(company, start_date, days):
    """Resources and the bookings visible in [start_date, start_date + days) for the calendar."""
    tz = timezone.get_current_timezone()
    from datetime import datetime, time
    window_start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    window_end = window_start + timedelta(days=days)
    span = (window_end - window_start).total_seconds()
    resources = list(BookableResource.objects.for_company(company).filter(is_active=True))
    bookings = (Booking.objects.for_company(company).filter(status__in=("reserved", "checked_in", "completed"),
                start__lt=window_end, end__gt=window_start).select_related("customer"))
    by_resource = {}
    now = timezone.now()
    for b in bookings:
        left = max((b.start - window_start).total_seconds(), 0) / span * 100
        right = min((b.end - window_start).total_seconds(), span) / span * 100
        late = b.status == "checked_in" and b.end < now
        by_resource.setdefault(b.resource_id, []).append({
            "booking": b, "left": round(left, 3), "width": round(max(right - left, 0.8), 3), "late": late})
    return [{"resource": r, "bars": by_resource.get(r.pk, [])} for r in resources], window_start, window_end
