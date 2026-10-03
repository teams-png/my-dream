"""
Online booking requests from a business's own website (form widget / WordPress plugin) or its
BookPilot booking page. A request never books anything by itself: staff confirm it, which creates
the real table reservation or resource booking (or opens the appointment form already filled in),
or decline it. Every lookup starts from the BookingSite, so a request only reaches its own business.
"""
import re

from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.text import slugify

from .models import BookableResource, BookingSite, OnlineBooking


def booking_kind(company):
    """appointment / resource / table / event, or None for businesses that don't take bookings."""
    if company is None:
        return None
    from apps.modules.catalog import online_booking_kind
    return online_booking_kind(company.business_type.code)


def _digits(phone):
    return re.sub(r"\D", "", phone or "")


def site_for(company):
    site = BookingSite.objects.filter(company=company).first()
    if site:
        return site
    base = slugify(company.slug or company.name)[:50] or f"business-{company.pk}"
    slug, n = base, 2
    while BookingSite.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return BookingSite.objects.create(company=company, slug=slug, whatsapp=company.phone or "",
                                      headline=f"Book with {company.name}"[:200])


def public_site(slug):
    site = BookingSite.objects.select_related("company", "company__business_type").filter(
        slug=slug, enabled=True, company__is_active=True).first()
    return site if site and booking_kind(site.company) else None


# ------------------------------------------------------------------ what can be booked

def _service_model(company):
    code = company.business_type.code
    if code == "spa":
        from apps.verticals.spa.models import SpaService
        return SpaService
    if code == "beauty_parlour":
        from apps.verticals.beauty_parlour.models import BeautyService
        return BeautyService
    if code == "vehicle_wash":
        from apps.verticals.vehicle_wash.models import WashPackage
        return WashPackage
    if code == "gym":
        from apps.verticals.gym.models import MembershipPlan
        return MembershipPlan
    from apps.verticals.saloon.models import SaloonService
    return SaloonService


def items(company, kind=None):
    """[{id, name, price, unit, minutes, capacity}] the customer can choose from."""
    kind = kind or booking_kind(company)
    if kind == "resource":
        return [{"id": r.id, "name": r.name, "price": f"{r.rate:.0f}" if r.rate else "", "unit": r.rate_unit,
                 "capacity": r.capacity, "details": r.details}
                for r in BookableResource.objects.for_company(company).filter(is_active=True)]
    if kind == "appointment":
        model = _service_model(company)
        out = []
        for s in model.objects.for_company(company).filter(is_active=True).order_by("name")[:200]:
            out.append({"id": s.id, "name": str(s) if model.__name__ == "WashPackage" else s.name,
                        "price": f"{s.price:.0f}" if getattr(s, "price", None) else "",
                        "minutes": getattr(s, "duration_minutes", None)})
        return out
    return []


def _find_item(company, kind, item_id):
    if not item_id:
        return None
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return None
    if kind == "resource":
        return BookableResource.objects.for_company(company).filter(id=item_id, is_active=True).first()
    if kind == "appointment":
        return _service_model(company).objects.for_company(company).filter(id=item_id).first()
    return None


# ------------------------------------------------------------------ requests

def _when(site, day, at):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, at or time(9, 0)), tz)


@transaction.atomic
def create_request(site, data, source=""):
    company = site.company
    kind = booking_kind(company)
    if kind is None:
        raise ValidationError("Online booking is not available.")
    name = (data.get("name") or "").strip()[:150]
    phone = (data.get("phone") or "").strip()[:30]
    if not name or len(_digits(phone)) < 7:
        raise ValidationError("Enter your name and a phone / WhatsApp number.")
    try:
        day = parse_date((data.get("date") or "").strip())
        at = parse_time((data.get("time") or "").strip()) if data.get("time") else None
        end_day = parse_date((data.get("end_date") or "").strip()) if data.get("end_date") else None
        end_at = parse_time((data.get("end_time") or "").strip()) if data.get("end_time") else None
    except ValueError:
        day = None
    if not day:
        raise ValidationError("Choose a date.")
    today = timezone.localdate()
    if day < today:
        raise ValidationError("Choose a date from today onwards.")
    if day > today + timedelta(days=site.max_days_ahead):
        raise ValidationError(f"Bookings can be made up to {site.max_days_ahead} days ahead.")
    item = _find_item(company, kind, data.get("item"))
    if kind in ("appointment", "table") and at is None:
        raise ValidationError("Choose a time.")
    if at is not None and _when(site, day, at) < timezone.now() + timedelta(hours=site.min_notice_hours):
        raise ValidationError(f"Please book at least {site.min_notice_hours} hour(s) ahead.")
    if kind == "resource":
        if item is None and items(company, kind):
            raise ValidationError("Choose what you want to book.")
        unit = getattr(item, "rate_unit", "day")
        if unit in ("day", "night", "month") and (end_day is None or end_day <= day) and unit != "day":
            raise ValidationError("Choose the check-out / return date.")
        if end_day and end_day < day:
            raise ValidationError("The end date must be after the start date.")
    try:
        guests = max(1, min(int(data.get("guests") or 1), 5000))
    except (TypeError, ValueError):
        guests = 1
    if kind == "resource" and item is not None and item.capacity and guests > item.capacity:
        raise ValidationError(f"{item.name} takes at most {item.capacity} people.")
    item_name = (str(item) if item is not None else (data.get("item_name") or "")).strip()[:200]
    req = OnlineBooking.objects.create(
        company=company, kind=kind, name=name, phone=phone, email=(data.get("email") or "")[:254],
        item_id=getattr(item, "id", None), item_name=item_name, date=day, time=at, end_date=end_day, end_time=end_at,
        guests=guests, notes=(data.get("notes") or "").strip()[:2000], source=source[:120])
    req.number = f"OB-{req.pk:05d}"
    req.save(update_fields=["number"])
    _notify(site, req)
    return req


def _notify(site, req):
    from apps.notifications.services import notify
    when = f"{req.date:%d %b}" + (f" {req.time:%H:%M}" if req.time else "")
    try:
        notify(company=site.company, title=f"New online booking: {req.name} · {when}",
               message=f"{req.item_name or req.get_kind_display()} · {req.guests} · {req.phone}")
    except Exception:  # never lose a request because email failed
        pass


def customer_for(req):
    from apps.customers.models import Customer
    if req.customer_id:
        return req.customer
    digits = _digits(req.phone)
    found = None
    if len(digits) >= 8:
        for c in Customer.objects.for_company(req.company).filter(phone__icontains=digits[-8:]):
            if _digits(c.phone).endswith(digits[-8:]):
                found = c
                break
    customer = found or Customer.objects.create(company=req.company, name=req.name, phone=req.phone[:20],
                                                email=req.email or "")
    req.customer = customer
    req.save(update_fields=["customer"])
    return customer


def _done(req, user, status, linked=""):
    req.status, req.handled_by, req.handled_at = status, user, timezone.now()
    if linked:
        req.linked = linked
    req.save(update_fields=["status", "handled_by", "handled_at", "linked"])
    return req


def resource_times(req, resource):
    unit = resource.rate_unit
    if unit == "night":
        start = _when(None, req.date, req.time or time(14, 0))
        end = _when(None, req.end_date or req.date + timedelta(days=1), req.end_time or time(12, 0))
    elif unit in ("day", "month"):
        start = _when(None, req.date, req.time or time(9, 0))
        end_day = req.end_date or req.date + timedelta(days=1 if unit == "day" else 30)
        end = _when(None, end_day, req.end_time or req.time or time(9, 0))
    else:  # hour / event
        start = _when(None, req.date, req.time or time(9, 0))
        end = _when(None, req.end_date or req.date, req.end_time) if req.end_time else start + timedelta(
            hours=1 if unit == "hour" else 4)
    return start, end


@transaction.atomic
def confirm(req, user, table=None, resource=None):
    """Creates the real record for tables and resources. Appointments/events are confirmed here and
    finished in their own booking form (staff, price, invoice)."""
    req = OnlineBooking.objects.select_for_update().get(pk=req.pk)
    if req.status != "new":
        raise ValidationError("This request has already been handled.")
    if req.kind == "table":
        from apps.verticals.restaurant.models import TableReservation
        res = TableReservation.objects.create(company=req.company, customer_name=req.name, phone=req.phone,
                                              reservation_at=_when(None, req.date, req.time), guest_count=req.guests,
                                              table=table, notes=(f"{req.number} " + req.notes)[:255])
        return _done(req, user, "confirmed", f"reservation:{res.pk}")
    if req.kind == "resource":
        from .bookings import create_booking
        resource = resource or _find_item(req.company, "resource", req.item_id)
        if resource is None:
            raise ValidationError("Choose which one to book.")
        start, end = resource_times(req, resource)
        booking = create_booking(company=req.company, user=user, resource=resource, customer=customer_for(req),
                                 start=start, end=end, guests=req.guests, notes=f"{req.number} {req.notes}".strip())
        return _done(req, user, "confirmed", f"booking:{booking.pk}")
    customer_for(req)
    return _done(req, user, "confirmed")


def decline(req, user, reason=""):
    if req.status != "new":
        raise ValidationError("This request has already been handled.")
    req.reply = reason[:255]
    req.save(update_fields=["reply"])
    return _done(req, user, "declined")


def reply_text(req, company, confirmed=True):
    when = f"{req.date:%d %b %Y}" + (f" {req.time:%H:%M}" if req.time else "")
    what = req.item_name or dict(OnlineBooking.KINDS)[req.kind]
    if confirmed:
        return f"Hello {req.name}, your booking with {company.name} is confirmed: {what}, {when}. Ref {req.number}. Thank you!"
    reason = f" ({req.reply})" if req.reply else ""
    return (f"Hello {req.name}, sorry, we can't confirm your request for {what} on {when}{reason}. "
            f"Please reply to choose another time. — {company.name}")
