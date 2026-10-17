"""Site workers (manpower supply): our workers placed at clients' sites.

* Each worker is an ordinary staff member (``Employee`` with ``worker_type="site"``) — so leave, salary advances,
  payslips and the payroll run work for them too. Their ID / passport / health card / licence are kept as staff
  documents with expiry dates (alerts at 30, 7 and 0 days come from the daily job).
* A site's daily timesheet is ordinary attendance with the site, hours and overtime hours.
* Pay: monthly salary, or per day / per hour worked (payroll counts the timesheet).
* Each month the client is billed per site: worked hours (or days, or a monthly rate per worker) × the rate,
  plus overtime — one invoice per site per month.
"""
import calendar
import re
from datetime import date as date_cls, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (Attendance, Employee, EmployeeDocument, HRSettings, SalaryStructure, SiteInvoice, SiteShift,
                     WorkSite)

CENT = Decimal("0.01")
ZERO = Decimal("0")
DOCS = [("id", "ID / residence card"), ("passport", "Passport"), ("health", "Health card"), ("licence", "Driving licence")]
DOC_NAMES = dict(DOCS)
SOON_DAYS = 30


def month_start(value=None):
    value = value or timezone.localdate()
    return value.replace(day=1)


def month_end(start):
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def expiry_state(day, today=None):
    if not day:
        return ""
    today = today or timezone.localdate()
    if day < today:
        return "expired"
    return "soon" if day <= today + timedelta(days=SOON_DAYS) else "ok"


# ------------------------------------------------------------------ documents

def documents(employee):
    """{kind: EmployeeDocument} for the worker's standard documents."""
    by_type = {d.document_type: d for d in EmployeeDocument.objects.for_company(employee.company).filter(employee=employee)}
    return {kind: by_type.get(name) for kind, name in DOCS}


def save_documents(employee, values):
    """values: {kind: (number, expiry_date)} — empty number and date removes that document."""
    company = employee.company
    for kind, name in DOCS:
        if kind not in values:
            continue
        number, expiry = values[kind]
        number = (number or "").strip()[:120]
        qs = EmployeeDocument.objects.for_company(company).filter(employee=employee, document_type=name)
        if not number and not expiry:
            qs.delete()
            continue
        doc = qs.first()
        if doc is None:
            EmployeeDocument.objects.create(company=company, employee=employee, document_type=name,
                                            document_number=number, expiry_date=expiry)
        elif (doc.document_number, doc.expiry_date) != (number, expiry):
            if doc.expiry_date != expiry:
                doc.alerts.all().delete()  # renewed: warn again before the new date
            doc.document_number, doc.expiry_date = number, expiry
            doc.save(update_fields=["document_number", "expiry_date"])


def expiring(company, days=60, today=None):
    """Active staff documents expired or expiring within ``days``, soonest first."""
    today = today or timezone.localdate()
    rows = list(EmployeeDocument.objects.for_company(company).filter(
        employee__is_active=True, expiry_date__isnull=False, expiry_date__lte=today + timedelta(days=days))
        .select_related("employee__site").order_by("expiry_date"))
    for doc in rows:
        doc.days_left = (doc.expiry_date - today).days
        doc.state = expiry_state(doc.expiry_date, today)
    return rows


# ------------------------------------------------------------------ workers

def workers(company, site=None):
    qs = Employee.objects.for_company(company).filter(worker_type="site", is_active=True).select_related("site")
    if site is not None:
        qs = qs.filter(site=site)
    return qs.order_by("name")


def assign(company, employees, site):
    """Move workers to a site (or off every site when ``site`` is None)."""
    if site is not None and site.company_id != company.id:
        raise ValidationError(_("Choose a site."))
    ids = [e.pk for e in employees if e.company_id == company.id]
    return Employee.objects.for_company(company).filter(pk__in=ids).update(site=site, worker_type="site")


@transaction.atomic
def worker_from_candidate(placement, site=None):
    """A recruitment candidate who joined becomes our site worker (once)."""
    candidate = placement.candidate
    company = placement.company
    existing = Employee.objects.for_company(company).filter(candidate=candidate).first()
    if existing:
        return existing, False
    salary = placement.offered_salary or placement.job_order.salary or ZERO
    worker = Employee.objects.create(
        company=company, name=candidate.name, phone=(candidate.phone or "")[:20],
        role_title=placement.job_order.position[:100], trade=(candidate.trade or placement.job_order.position)[:100],
        nationality=(candidate.nationality or "")[:60], worker_type="site", site=site, candidate=candidate,
        joined_date=placement.joining_date or timezone.localdate(), salary=salary)
    SalaryStructure.objects.create(company=company, employee=worker, basic_pay=salary, is_active=True)
    save_documents(worker, {"passport": (candidate.passport_no, candidate.passport_expiry)})
    if placement.visa_number or placement.visa_expiry:
        EmployeeDocument.objects.create(company=company, employee=worker, document_type="Work visa",
                                        document_number=placement.visa_number, expiry_date=placement.visa_expiry)
    return worker, True


# ------------------------------------------------------------------ timesheet

def _num(value, default=None):
    try:
        number = Decimal(str(value).strip())
    except Exception:
        return default
    if number < 0 or number > 24:
        raise ValidationError(_("Hours must be between 0 and 24."))
    return number.quantize(CENT)


@transaction.atomic
def save_day(company, site, day, rows):
    """rows: [(employee, status, hours, ot_hours)]; status "" clears the day for that worker at this site."""
    if site.company_id != company.id:
        raise ValidationError(_("Choose a site."))
    if day > timezone.localdate():
        raise ValidationError(_("You cannot mark attendance for a future date."))
    valid = dict(Attendance.STATUS)
    saved = 0
    for employee, status, hours, ot in rows:
        if employee.company_id != company.id:
            continue
        if not status:
            Attendance.objects.for_company(company).filter(employee=employee, date=day, site=site).delete()
            continue
        if status not in valid:
            continue
        hours = _num(hours) if hours not in (None, "") else None
        normal = day_hours(employee, site)
        if status == "present" and hours is None:
            hours = normal
        elif status == "half_day" and hours is None:
            hours = (normal / 2).quantize(CENT)
        elif status not in ("present", "half_day"):
            hours = None
        ot = _num(ot, ZERO) if ot not in (None, "") else ZERO
        if status not in ("present", "half_day"):
            ot = ZERO
        Attendance.objects.update_or_create(company=company, employee=employee, date=day, defaults={
            "status": status, "site": site, "hours": hours, "ot_hours": ot})
        saved += 1
    return saved


def day_hours(employee, site):
    """A normal day for this worker here: their shift's hours, else the site's."""
    shift = employee.duty_shift if employee.duty_shift_id else None
    if shift is not None and shift.site_id == site.id:
        return shift.hours
    return site.hours_per_day


def is_off(employee, day, company_off=()):
    if employee.weekly_off is not None:
        return day.weekday() == employee.weekly_off
    return day.weekday() in company_off


# ------------------------------------------------------------------ duty roster

def save_shift(site, name, start_time, end_time, needed, shift=None):
    name = (name or "").strip()[:60]
    if not name or start_time is None or end_time is None:
        raise ValidationError(_("Enter the shift name and its start and end time."))
    shift = shift or SiteShift(company=site.company, site=site)
    shift.name, shift.start_time, shift.end_time = name, start_time, end_time
    shift.needed = max(0, min(int(needed or 0), 999))
    shift.save()
    return shift


@transaction.atomic
def assign_duty(company, employees, shift, weekly_off=None):
    """Put workers on a shift (and so at its site); shift None takes them off their shift."""
    if shift is not None and shift.company_id != company.id:
        raise ValidationError(_("Choose a shift."))
    count = 0
    for worker in employees:
        if worker.company_id != company.id:
            continue
        worker.duty_shift = shift
        fields = ["duty_shift"]
        if shift is not None:
            worker.site, worker.worker_type = shift.site, "site"
            fields += ["site", "worker_type"]
        if weekly_off != "":
            worker.weekly_off = None if weekly_off in (None, "none") else int(weekly_off) % 7
            fields.append("weekly_off")
        worker.save(update_fields=fields)
        count += 1
    return count


def duty_board(company):
    """Sites with their shifts, who is on each and how many are short."""
    sites = list(WorkSite.objects.for_company(company).filter(is_active=True).prefetch_related("shifts"))
    staff = list(workers(company).select_related("duty_shift"))
    by_shift = {}
    for w in staff:
        if w.duty_shift_id:
            by_shift.setdefault(w.duty_shift_id, []).append(w)
    for site in sites:
        site.shift_rows = []
        for shift in site.shifts.all():
            people = by_shift.get(shift.id, [])
            site.shift_rows.append({"shift": shift, "workers": people, "short": max(0, shift.needed - len(people))})
        site.no_shift = [w for w in staff if w.site_id == site.id and not w.duty_shift_id]
        site.short = sum(r["short"] for r in site.shift_rows)
    return sites, [w for w in staff if not w.site_id]


# ------------------------------------------------------------------ cost and profit

def structure_of(employee):
    return getattr(employee, "salary_structure", None)


def pay_cost(employee, days, hours, ot, month_days):
    """What the worker costs us for this time: their pay for the days / hours (monthly salary pro rata)
    plus overtime at their overtime rate."""
    from .services import _money_total
    st = structure_of(employee)
    basic = st.basic_pay if st else (employee.salary or ZERO)
    allowances = _money_total(st.allowances) if st else ZERO
    ot_rate = st.overtime_hourly_rate if st else ZERO
    if employee.pay_basis == "daily":
        normal = basic * days
    elif employee.pay_basis == "hourly":
        normal = basic * hours
    else:
        normal = (basic + allowances) * min(Decimal("1"), days / Decimal(month_days or 1))
    ot_pay = (ot or ZERO) * ot_rate
    return normal.quantize(CENT), ot_pay.quantize(CENT)


def site_profit(site, start):
    """site_month with what each worker costs and the profit on them."""
    rows = site_month(site, start)
    month_days = working_days(site.company, start)
    for row in rows:
        normal, ot_pay = pay_cost(row["employee"], row["days"], row["hours"], row["ot"], month_days)
        row.update(pay=normal, ot_pay=ot_pay, cost=normal + ot_pay)
        row["profit"] = row["amount"] - row["cost"]
    return rows


def profit_report(company, start):
    sites = []
    for site in WorkSite.objects.for_company(company).select_related("client"):
        rows = site_profit(site, start)
        if not rows:
            continue
        billed = sum((r["amount"] for r in rows), ZERO)
        cost = sum((r["cost"] for r in rows), ZERO)
        site.rows, site.billed, site.cost, site.profit = rows, billed, cost, billed - cost
        site.margin = round(100 * (billed - cost) / billed) if billed else 0
        sites.append(site)
    billed = sum((s.billed for s in sites), ZERO)
    cost = sum((s.cost for s in sites), ZERO)
    return sites, {"billed": billed, "cost": cost, "profit": billed - cost,
                   "margin": round(100 * (billed - cost) / billed) if billed else 0,
                   "ot": sum((r["ot"] for s in sites for r in s.rows), ZERO),
                   "ot_pay": sum((r["ot_pay"] for s in sites for r in s.rows), ZERO)}


def worker_month(employee, start):
    """This worker's month, site by site: days, hours, overtime, what we pay and what the client is billed."""
    end = month_end(start)
    site_ids = set(Attendance.objects.for_company(employee.company).filter(
        employee=employee, date__range=(start, end), site__isnull=False).values_list("site_id", flat=True))
    rows = []
    for site in WorkSite.objects.for_company(employee.company).filter(id__in=site_ids):
        for row in site_profit(site, start):
            if row["employee"].pk == employee.pk:
                row["site"] = site
                rows.append(row)
    keys = ("days", "hours", "ot", "pay", "ot_pay", "cost", "amount", "profit")
    total = {k: sum((r[k] for r in rows), ZERO) for k in keys}
    return rows, total


# ------------------------------------------------------------------ timesheet

CODES = {"present": "P", "absent": "A", "half_day": "½", "leave": "L", "holiday": "H"}


def timesheet(site, start):
    """Worker × day grid for the month at this site (for the client to sign)."""
    end = month_end(start)
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    marks = {}
    for m in Attendance.objects.for_company(site.company).filter(site=site, date__range=(start, end)):
        marks[(m.employee_id, m.date)] = m
    totals = {r["employee"].pk: r for r in site_month(site, start)}
    people = {w.pk: w for w in workers(site.company, site)}
    for pk in totals:
        people.setdefault(pk, totals[pk]["employee"])
    rows = []
    for w in sorted(people.values(), key=lambda e: e.name.lower()):
        cells = []
        for d in days:
            m = marks.get((w.pk, d))
            if m is None:
                cells.append({"code": "", "hours": None, "ot": None})
            else:
                cells.append({"code": CODES.get(m.status, ""), "hours": m.hours, "ot": m.ot_hours or None})
        t = totals.get(w.pk, {"days": ZERO, "hours": ZERO, "ot": ZERO})
        rows.append({"employee": w, "cells": cells, "days": t["days"], "hours": t["hours"], "ot": t["ot"]})
    return days, rows


# ------------------------------------------------------------------ client billing

def working_days(company, start):
    off = set(HRSettings.load(company).weekly_off_days or [])
    end = month_end(start)
    return sum(1 for n in range((end - start).days + 1) if (start + timedelta(days=n)).weekday() not in off) or 1


def site_month(site, start):
    """Per worker who worked at this site in the month: days, hours, OT and the amount to bill."""
    end = month_end(start)
    marks = Attendance.objects.for_company(site.company).filter(site=site, date__range=(start, end)).select_related("employee")
    rows = {}
    for mark in marks:
        row = rows.setdefault(mark.employee_id, {"employee": mark.employee, "days": ZERO, "hours": ZERO, "ot": ZERO})
        if mark.status in ("present", "half_day"):
            part = Decimal("1") if mark.status == "present" else Decimal("0.5")
            row["days"] += part
            row["hours"] += mark.hours if mark.hours is not None else site.hours_per_day * part
        row["ot"] += mark.ot_hours or ZERO
    month_days = Decimal(working_days(site.company, start)) if site.bill_basis == "month" else None
    out = []
    for row in rows.values():
        rate = row["employee"].bill_rate if row["employee"].bill_rate is not None else site.bill_rate
        if site.bill_basis == "hour":
            qty = row["hours"]
        elif site.bill_basis == "day":
            qty = row["days"]
        else:
            qty = min(Decimal("1"), (row["days"] / month_days)).quantize(Decimal("0.001"))
        row.update(rate=rate, qty=qty, normal=(qty * rate).quantize(CENT),
                   ot_amount=(row["ot"] * site.ot_bill_rate).quantize(CENT))
        row["amount"] = row["normal"] + row["ot_amount"]
        if row["days"] or row["ot"]:
            out.append(row)
    out.sort(key=lambda r: r["employee"].name.lower())
    return out


def _slug(text):
    return re.sub(r"[^A-Z0-9]+", "-", (text or "").upper()).strip("-")[:16] or "WORKER"


@transaction.atomic
def bill_site(company, user, site, start):
    """One invoice to the site's client for the month: a line per trade and rate, plus overtime."""
    from apps.industry.common import invoice as make_invoice, service_product
    site = WorkSite.objects.select_for_update().get(pk=site.pk, company=company)
    start = month_start(start)
    if site.client_id is None:
        raise ValidationError(_("Choose the client for this site first."))
    if start > month_start():
        raise ValidationError(_("This month has not started yet."))
    if SiteInvoice.objects.for_company(company).filter(site=site, month=start).exists():
        raise ValidationError(_("This site is already billed for %(month)s.") % {"month": start.strftime("%b %Y")})
    rows = site_month(site, start)
    unit = {"hour": "hrs", "day": "days", "month": "month"}[site.bill_basis]
    groups = {}
    ot_hours = ZERO
    for row in rows:
        trade = row["employee"].trade or row["employee"].role_title or "Manpower"
        key = (trade, row["rate"])
        groups[key] = groups.get(key, ZERO) + row["qty"]
        ot_hours += row["ot"]
    lines = []
    for (trade, rate), qty in sorted(groups.items()):
        if qty > 0 and rate > 0:
            product = service_product(company, f"MP-{site.pk}-{_slug(trade)}-{site.bill_basis[0].upper()}{int(rate * 100)}",
                                      f"{trade} · {site.name} ({unit})")
            lines.append((product, qty, rate))
    if ot_hours > 0 and site.ot_bill_rate > 0:
        lines.append((service_product(company, f"MP-{site.pk}-OT", f"Overtime hours · {site.name}"), ot_hours, site.ot_bill_rate))
    if not lines:
        raise ValidationError(_("Nothing to bill: no attendance or no rate for %(month)s.") % {"month": start.strftime("%b %Y")})
    inv = make_invoice(company, user, site.client, lines, date=min(month_end(start), timezone.localdate()))
    try:
        with transaction.atomic():
            SiteInvoice.objects.create(company=company, site=site, month=start, invoice=inv, amount=inv.total)
    except IntegrityError:
        raise ValidationError(_("This site is already billed for %(month)s.") % {"month": start.strftime("%b %Y")})
    return inv


def overview(company, today=None):
    today = today or timezone.localdate()
    staff = workers(company)
    docs = expiring(company, days=SOON_DAYS, today=today)
    return {
        "workers": staff.count(),
        "unassigned": staff.filter(site__isnull=True).count(),
        "sites": WorkSite.objects.for_company(company).filter(is_active=True).count(),
        "present": Attendance.objects.for_company(company).filter(
            date=today, status__in=["present", "half_day"], employee__worker_type="site", employee__is_active=True).count(),
        "expired": sum(1 for d in docs if d.state == "expired"),
        "soon": sum(1 for d in docs if d.state == "soon"),
    }


def parse_month(value):
    try:
        year, month = (int(x) for x in (value or "").split("-")[:2])
        return date_cls(year, month, 1)
    except (TypeError, ValueError):
        return month_start()
