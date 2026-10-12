"""What a job card records for a few kinds of business, kept in ``ServiceCase.record`` (JSON):

* clinic  — vitals, complaint, diagnosis, prescription lines, advice, next visit (print: prescription)
* lab     — test results with unit and normal range; out-of-range values are flagged (print: report)
* eye     — eye test (power for right and left eye), PD, frame and lens (print: eye prescription / order)
* laundry — every piece gets a tag number from the job's lines (print: tag slips)
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
MAX_ROWS = 25


def kind_for(company):
    if company is None or not company.business_type_id:
        return None
    feats = business_features(company.business_type.code)
    for kind, feat in (("clinic", "clinic"), ("lab", "lab"), ("eye", "eye_test"), ("laundry", "laundry")):
        if feat in feats:
            return kind
    return None


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


def save(job, post, kind):
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
    else:
        raise ValidationError(_("Nothing to record for this business."))
    rec["saved_at"] = timezone.now().isoformat()
    job.record = rec
    job.save(update_fields=["record"])
    return rec


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

