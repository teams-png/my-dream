"""What a job card records for a few kinds of business, kept in ``ServiceCase.record`` (JSON):

* clinic  — vitals, complaint, diagnosis, prescription lines, advice, next visit (print: prescription)
* lab     — test results with unit and normal range; out-of-range values are flagged (print: report)
* eye     — eye test (power for right and left eye), PD, frame and lens (print: eye prescription / order)
* laundry — every piece gets a tag number from the job's lines (print: tag slips)
* vehicle — garage check-in: km reading, fuel, a check-list, body damage, things left in the car and the next
            service (km / date); shown on the job card print and the customer's status page
* device  — computer / printer check-in: what came with it (charger, bag, cartridge …), its condition, the printer's
            page counter, warranty and the customer's OK that data may be lost; shown on the job card print
* cake    — a bakery's cake order: flavour, weight, shape, eggless, the message on the cake, design notes and the
            advance paid (recorded as a payment at once and set against the bill at pickup)
"""
import re
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.modules.catalog import business_features

VITALS = ("bp", "pulse", "temp", "weight", "spo2", "sugar")
EYE_FIELDS = ("sph", "cyl", "axis", "add", "va")
FUEL_LEVELS = ("", "empty", "1/4", "1/2", "3/4", "full")
VEHICLE_CHECKS = (("engine_oil", "Engine oil"), ("brakes", "Brakes"), ("tyres", "Tyres"), ("battery", "Battery"),
                  ("lights", "Lights"), ("ac", "AC"), ("coolant", "Coolant"), ("wipers", "Wipers"))
CHECK_STATES = ("", "ok", "attention", "replaced")
DEVICE_ITEMS = (("charger", "Charger / adapter"), ("bag", "Bag"), ("power_cable", "Power cable"),
                ("usb_cable", "USB cable"), ("cartridge", "Cartridge / toner"), ("battery", "Battery"))
WARRANTY = ("", "in", "out")
CAKE_SHAPES = ("", "round", "square", "heart", "photo", "tier")
ADVANCE_METHODS = ("cash", "card", "bank")
MAX_ROWS = 25


def kind_for(company):
    if company is None or not company.business_type_id:
        return None
    feats = business_features(company.business_type.code)
    for kind, feat in (("clinic", "clinic"), ("lab", "lab"), ("eye", "eye_test"), ("laundry", "laundry")):
        if feat in feats:
            return kind
    if company.business_type.code in VEHICLE_TYPES:
        return "vehicle"
    if company.business_type.code in DEVICE_TYPES:
        return "device"
    if "cake_orders" in feats:
        return "cake"
    return None


VEHICLE_TYPES = {"auto_garage"}
DEVICE_TYPES = {"computer_shop", "electronics_store", "computer_repair", "electronics_repair"}


def _txt(post, key, limit=500):
    return (post.get(key) or "").strip()[:limit]


def _rows(post, prefix, keys, limit=200):
    cols = [post.getlist(f"{prefix}_{k}") for k in keys]
    rows = []
    for values in zip(*cols):
        row = {k: (v or "").strip()[:limit] for k, v in zip(keys, values)}
        if any(row.values()):
            rows.append(row)
    return rows[:MAX_ROWS]


def _flag(value, normal):
    """'H' / 'L' when a number is outside a "low-high" or "<x" / ">x" range."""
    try:
        v = float(str(value).replace(",", ""))
    except ValueError:
        return ""
    normal = (normal or "").replace(" ", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[-–](-?\d+(?:\.\d+)?)", normal)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return "H" if v > hi else "L" if v < lo else ""
    m = re.fullmatch(r"<(-?\d+(?:\.\d+)?)", normal)
    if m:
        return "H" if v >= float(m.group(1)) else ""
    m = re.fullmatch(r">(-?\d+(?:\.\d+)?)", normal)
    if m:
        return "L" if v <= float(m.group(1)) else ""
    return ""


def save(job, post, kind, user=None):
    """Saves the record form of this job's kind. Returns the record."""
    if job.status == "cancelled":
        raise ValidationError(_("This job is cancelled."))
    rec = dict(job.record or {})
    if kind == "clinic":
        rec["vitals"] = {k: _txt(post, f"v_{k}", 20) for k in VITALS}
        rec["complaint"] = _txt(post, "complaint", 2000)
        rec["diagnosis"] = _txt(post, "diagnosis", 2000)
        rec["advice"] = _txt(post, "advice", 2000)
        rec["rx"] = _rows(post, "rx", ("medicine", "dose", "freq", "days", "note"))
        nv = parse_date(post.get("next_visit") or "")
        rec["next_visit"] = nv.isoformat() if nv else ""
    elif kind == "lab":
        rows = _rows(post, "res", ("test", "value", "unit", "range"))
        for r in rows:
            r["flag"] = _flag(r["value"], r["range"])
        rec["results"] = rows
        rec["sample"] = _txt(post, "sample", 200)
        rec["remarks"] = _txt(post, "remarks", 2000)
    elif kind == "eye":
        rec["eye"] = {side: {f: _txt(post, f"{side}_{f}", 10) for f in EYE_FIELDS} for side in ("R", "L")}
        rec["pd"] = _txt(post, "pd", 10)
        rec["frame"] = _txt(post, "frame", 200)
        rec["lens"] = _txt(post, "lens", 200)
        rec["notes"] = _txt(post, "eye_notes", 1000)
        # the latest eye power is kept on the customer's record too
        profile = job.profile
        details = dict(profile.details or {})
        details["eye_rx"] = {"date": timezone.localdate().isoformat(), "job": job.number, **rec["eye"], "pd": rec["pd"]}
        profile.details = details
        profile.save(update_fields=["details"])
    elif kind == "vehicle":
        km = re.sub(r"[^0-9]", "", _txt(post, "km_in", 12))
        next_km = re.sub(r"[^0-9]", "", _txt(post, "next_km", 12))
        fuel = _txt(post, "fuel", 10)
        rec["km_in"] = km
        rec["fuel"] = fuel if fuel in FUEL_LEVELS else ""
        rec["checks"] = {key: (post.get(f"chk_{key}") if post.get(f"chk_{key}") in CHECK_STATES else "")
                         for key, _label in VEHICLE_CHECKS}
        rec["damage"] = _txt(post, "damage", 1000)
        rec["belongings"] = _txt(post, "belongings", 500)
        rec["next_km"] = next_km
        nd = parse_date(post.get("next_date") or "")
        rec["next_date"] = nd.isoformat() if nd else ""
        # the car's last reading and next service stay on its record for the next visit and the reminders
        profile = job.profile
        details = dict(profile.details or {})
        details["vehicle"] = {"date": timezone.localdate().isoformat(), "job": job.number, "km": km,
                              "next_km": next_km, "next_date": rec["next_date"]}
        profile.details = details
        profile.save(update_fields=["details"])
    elif kind == "device":
        rec["items"] = [key for key, _label in DEVICE_ITEMS if post.get(f"item_{key}")]
        rec["condition"] = _txt(post, "condition", 1000)
        rec["counter"] = re.sub(r"[^0-9]", "", _txt(post, "counter", 12))
        warranty = _txt(post, "warranty", 5)
        rec["warranty"] = warranty if warranty in WARRANTY else ""
        rec["data_ok"] = bool(post.get("data_ok"))
    elif kind == "cake":
        rec["flavour"] = _txt(post, "flavour", 100)
        weight = re.sub(r"[^0-9.]", "", _txt(post, "weight_kg", 10))
        rec["weight_kg"] = weight
        shape = _txt(post, "shape", 10)
        rec["shape"] = shape if shape in CAKE_SHAPES else ""
        rec["eggless"] = bool(post.get("eggless"))
        rec["message"] = _txt(post, "message", 200)
        rec["design"] = _txt(post, "design", 1000)
        advance = _money_or_none(post.get("advance"))
        if advance and not rec.get("advance_payment_id"):
            # the advance is money in hand today: a payment on the customer's account, set against the bill later
            from apps.sales.services import record_customer_payment
            method = post.get("advance_method") if post.get("advance_method") in ADVANCE_METHODS else "cash"
            payment = record_customer_payment(company=job.company, user=user, customer=job.profile.customer,
                                              amount=advance, date=timezone.localdate(), method=method)
            rec.update(advance=str(payment.amount), advance_method=method, advance_payment_id=payment.id)
    else:
        raise ValidationError(_("Nothing to record for this business."))
    rec["saved_at"] = timezone.now().isoformat()
    job.record = rec
    job.save(update_fields=["record"])
    return rec


def vehicle_checks(rec):
    """[(label, state)] of the check-list, in order, for the form and the print."""
    checks = (rec or {}).get("checks") or {}
    return [(key, _(label), checks.get(key, "")) for key, label in VEHICLE_CHECKS]


def _money_or_none(value):
    from decimal import Decimal, InvalidOperation
    try:
        v = Decimal(str(value or "").replace(",", "").strip() or "0")
    except InvalidOperation:
        raise ValidationError(_("Type the advance as a number."))
    if v < 0:
        raise ValidationError(_("The advance cannot be negative."))
    return v.quantize(Decimal("0.01")) if v else None


def device_items(rec):
    """[(key, label, received)] of the things that came with the device."""
    got = set((rec or {}).get("items") or [])
    return [(key, _(label), key in got) for key, label in DEVICE_ITEMS]


def previous_vehicle(job):
    """The car's last visit before this job (its km reading and what was due next)."""
    from apps.verticals.saloon.models import ServiceCase
    for other in (ServiceCase.objects.for_company(job.company).filter(profile=job.profile)
                  .exclude(pk=job.pk).order_by("-opened_date", "-id")[:10]):
        if (other.record or {}).get("km_in"):
            return other
    return None


def previous_visits(job, limit=5):
    """The patient's earlier visits with a record (newest first): date, doctor, diagnosis and medicines."""
    from apps.verticals.saloon.models import ServiceCase
    visits = []
    for other in (ServiceCase.objects.for_company(job.company).filter(profile=job.profile)
                  .exclude(pk=job.pk).select_related("assigned_staff").order_by("-opened_date", "-id")[:limit * 3]):
        rec = other.record or {}
        if rec.get("diagnosis") or rec.get("rx") or rec.get("complaint"):
            visits.append(other)
        if len(visits) >= limit:
            break
    return visits


def previous_eye(job):
    """The last eye test of this customer before this job (to compare)."""
    from apps.verticals.saloon.models import ServiceCase
    for other in (ServiceCase.objects.for_company(job.company).filter(profile__customer=job.profile.customer)
                  .exclude(pk=job.pk).order_by("-opened_date", "-id")[:10]):
        if (other.record or {}).get("eye"):
            return other
    return None


def laundry_tags(job):
    """One tag per piece: JOB-00012-1, -2 … with what it is."""
    tags, n = [], 0
    for line in job.lines.all():
        pieces = max(1, int(line.quantity)) if line.quantity == int(line.quantity) else 1
        for _i in range(min(pieces, 200)):
            n += 1
            tags.append({"tag": f"{job.number}-{n}", "item": line.description})
    return tags


def book_follow_up(job, when_date):
    """A new booked job for the next visit, same patient and doctor."""
    from . import jobs
    if when_date is None or when_date < timezone.localdate():
        raise ValidationError(_("Choose a date from today on."))
    at = timezone.make_aware(datetime.combine(when_date, timezone.localtime(job.scheduled_at).time()
                                              if job.scheduled_at else time(10, 0)))
    title = job.title if job.title.lower().startswith(_("follow-up").lower()) else _("Follow-up: %(title)s") % {"title": job.title}
    new = jobs.create_job(job.company, customer=job.profile.customer, title=title[:200],
                          subject_name=job.profile.subject_name, identifier=job.profile.identifier,
                          staff=job.assigned_staff, scheduled_at=at, duration=job.duration_minutes,
                          description=_("Follow-up of %(number)s") % {"number": job.number})
    return new

