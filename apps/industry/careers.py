"""
Careers website for a recruitment agency: open jobs and an apply form.

Every lookup starts from the CareersSite (found by its own slug or API key), so an
application can only ever reach the agency that owns that site.
"""
import re
import secrets

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import Candidate, CareersSite, JobOrder, Placement

CV_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"}
CV_MAX_BYTES = 8 * 1024 * 1024


def site_for(company):
    site = CareersSite.objects.filter(company=company).first()
    if site:
        return site
    base = slugify(company.slug or company.name)[:50] or f"agency-{company.pk}"
    slug, n = base, 2
    while CareersSite.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return CareersSite.objects.create(company=company, slug=slug, headline=f"Jobs with {company.name}"[:200],
                                      whatsapp=company.phone or "", email=company.email or "",
                                      address=(company.address or "")[:255], api_key=secrets.token_urlsafe(30)[:40])


def public_site(slug):
    return CareersSite.objects.select_related("company").filter(slug=slug, enabled=True, company__is_active=True).first()


def receiving_site(slug, widget=False):
    """A site that accepts applications: its own BookPilot page is live, the agency connected its own website,
    or (widget=True) the agency's application form is placed on any website."""
    site = CareersSite.objects.select_related("company").filter(
        slug=slug, company__is_active=True).first()
    if site and (widget or site.enabled or site.allowed_origins.strip()):
        return site
    return None


def match_job(site, value):
    """A job id, or a position title typed/selected on the agency's own career page."""
    value = (value or "").strip()
    if not value:
        return None
    jobs = JobOrder.objects.for_company(site.company).filter(status="open")
    if value.isdigit():
        return jobs.filter(id=int(value)).first()
    return jobs.filter(position__iexact=value[:150]).order_by("-created_at").first()


def public_jobs(site):
    return (JobOrder.objects.for_company(site.company).filter(status="open", publish_online=True)
            .order_by("-created_at"))


def public_job(site, job_id):
    return public_jobs(site).filter(id=job_id).first()


def origins(site):
    return {o.strip().rstrip("/") for o in site.allowed_origins.splitlines() if o.strip()}


def _digits(phone):
    return re.sub(r"\D", "", phone or "")


def check_cv(upload):
    if not upload:
        return None
    ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if ext not in CV_EXTENSIONS:
        raise ValidationError("Upload your CV as PDF, Word or a photo.")
    if upload.size > CV_MAX_BYTES:
        raise ValidationError("The CV file is too large (max 8 MB).")
    return upload


def _find_existing(company, passport, phone):
    qs = Candidate.objects.for_company(company)
    if passport:
        found = qs.filter(passport_no__iexact=passport).first()
        if found:
            return found
    digits = _digits(phone)
    if len(digits) >= 8:
        for cand in qs.filter(phone__icontains=digits[-8:]):
            if _digits(cand.phone).endswith(digits[-8:]):
                return cand
    return None


@transaction.atomic
def apply(site, data, cv=None, job=None, source_note=""):
    """data: name, phone, email, nationality, passport_no, trade, experience_years, current_location, message.
    Returns (candidate, placement or None, is_new_candidate)."""
    company = site.company
    name = (data.get("name") or "").strip()[:150]
    phone = (data.get("phone") or "").strip()[:30]
    if not name or len(_digits(phone)) < 7:
        raise ValidationError("Enter your full name and a phone / WhatsApp number.")
    passport = (data.get("passport_no") or "").strip().upper()[:30]
    if site.ask_passport and not passport:
        raise ValidationError("Enter your passport number.")
    cv = check_cv(cv)
    try:
        years = round(float(data.get("experience_years") or 0), 1) or None
    except (TypeError, ValueError):
        years = None
    note = (data.get("message") or "").strip()[:2000]
    extra = _extra_lines(data)
    if extra:
        note = (note + "\n" if note else "") + extra
    note = note or (f"Applied via {source_note}" if source_note else "")
    details = _details(data)
    stamp = f"[{timezone.localdate():%d %b %Y} {source_note or 'website'}] "
    candidate = _find_existing(company, passport, phone)
    is_new = candidate is None
    if is_new:
        candidate = Candidate.objects.create(
            company=company, name=name, phone=phone, email=(data.get("email") or "")[:254],
            nationality=(data.get("nationality") or "")[:100], passport_no=passport,
            trade=(data.get("trade") or (job.position if job else ""))[:150], experience_years=years,
            current_location=(data.get("current_location") or "")[:150], source="website",
            notes=(stamp + note) if note else "", **details)
        candidate.number = f"CN-{candidate.pk:05d}"
        candidate.save(update_fields=["number"])
    else:
        # fill in only what we did not have; never overwrite what the office entered
        for field, value in (("email", data.get("email")), ("nationality", data.get("nationality")),
                             ("passport_no", passport), ("trade", data.get("trade")),
                             ("current_location", data.get("current_location"))):
            if value and not getattr(candidate, field):
                setattr(candidate, field, str(value).strip()[:150])
        if years and not candidate.experience_years:
            candidate.experience_years = years
        for field, value in details.items():
            if value not in (None, "", False) and not getattr(candidate, field):
                setattr(candidate, field, value)
        if note:
            candidate.notes = (candidate.notes + "\n" if candidate.notes else "") + stamp + note
        candidate.save()
    if cv:
        candidate.cv.save(f"{candidate.number or candidate.pk}-{cv.name[-60:]}", cv, save=True)
    placement = None
    if job is not None:
        try:
            with transaction.atomic():
                placement = Placement.objects.create(company=company, job_order=job, candidate=candidate, stage="applied",
                                                     fee=job.fee_per_placement, offered_salary=job.salary)
        except IntegrityError:
            placement = Placement.objects.get(job_order=job, candidate=candidate)
        if candidate.status == "available":
            Candidate.objects.filter(pk=candidate.pk).update(status="in_process")
    _notify(site, candidate, job, is_new)
    return candidate, placement, is_new


EXTRA_FIELDS = [("marital_status", "Marital status"), ("driving_licence", "Driving licence"),
                ("notice_period", "Can join"), ("current_salary", "Current salary"), ("visa_status", "Visa status"),
                ("religion", "Religion"), ("height", "Height"), ("referral", "Heard about us")]


def _extra_lines(data):
    lines = []
    for key, label in EXTRA_FIELDS:
        value = (data.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value[:200]}")
    return "\n".join(lines)


def _details(data):
    """Optional profile fields from the detailed form, validated loosely (bad values are skipped, never rejected)."""
    from datetime import date as date_cls
    from decimal import Decimal, InvalidOperation
    from django.utils.dateparse import parse_date
    out = {}
    gender = (data.get("gender") or "").strip().lower()
    if gender in ("male", "female"):
        out["gender"] = gender
    for field in ("date_of_birth", "passport_expiry"):
        try:
            day = parse_date((data.get(field) or "").strip())
        except ValueError:
            day = None
        if day and date_cls(1930, 1, 1) <= day <= date_cls(2100, 1, 1):
            out[field] = day
    try:
        salary = Decimal(str(data.get("expected_salary") or "").replace(",", "").strip() or "0")
        if 0 < salary < Decimal("10000000"):
            out["expected_salary"] = salary.quantize(Decimal("0.01"))
    except InvalidOperation:
        pass
    if str(data.get("gulf_experience") or "").strip().lower() in ("yes", "on", "true", "1"):
        out["gulf_experience"] = True
    for field, size in (("education", 150), ("languages", 150)):
        value = (data.get(field) or "").strip()
        if value:
            out[field] = value[:size]
    return out


def _notify(site, candidate, job, is_new):
    from apps.notifications.services import notify
    what = f"{job.number} {job.position}" if job else "general application"
    try:
        notify(company=site.company, title=f"New online application: {candidate.name}",
               message=f"{what} · {candidate.phone}{'' if is_new else ' (existing candidate)'}")
    except Exception:  # an email problem must never lose an application
        pass
