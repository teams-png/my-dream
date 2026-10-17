"""Advanced HR features a business switches on in HR settings (all off by default, so the menus stay small):

* wps        — WPS salary file (Qatar Wage Protection System .SIF/CSV) from an approved payroll
* settlement — end-of-service gratuity and the final settlement (salary, leave pay, ticket, less advances)
* vacation   — annual vacation (home leave) with the air ticket: who is away, who is due, who is late back
* camps      — staff camps / accommodation and their monthly cost per head (used in site profit)
* visa_quota — recruitment: visa quotas approved by the ministry, used and left
* sub_agents — recruitment: commission owed to sub-agents for the candidates they sent
"""
import csv
import io
from datetime import date as date_cls, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from .models import (AdvanceRecovery, Attendance, Employee, EmployeeDocument, FinalSettlement, HRSettings, PayrollLine,
                     SalaryAdvance, Vacation)

ZERO = Decimal("0")
CENT = Decimal("0.01")

# code, label, one-line explanation, needs this industry feature ("" = every business)
EXTRAS = [
    ("wps", _l("WPS salary file"), _l("Download the bank's WPS salary file (SIF) from an approved payroll."), ""),
    ("settlement", _l("Gratuity & final settlement"),
     _l("End-of-service gratuity and the final settlement when someone leaves, recorded in the accounts."), ""),
    ("vacation", _l("Vacation & air ticket"),
     _l("Annual home leave with the air ticket: who is away, due or late back."), ""),
    ("camps", _l("Camps & accommodation cost"),
     _l("Staff camps with their monthly cost per head, counted in site profit."), "manpower"),
    ("visa_quota", _l("Visa quota"), _l("Visa quotas approved for the company: used and left."), "recruitment"),
    ("sub_agents", _l("Sub-agent commission"),
     _l("What each sub-agent is owed for the candidates they sent, and what is paid."), "recruitment"),
]
CODES = {code for code, *_rest in EXTRAS}


def available(company):
    from apps.webapp.industry_access import company_features
    feats = company_features(company)
    return [(code, label, help_text) for code, label, help_text, need in EXTRAS if not need or need in feats]


def enabled(company, code=None):
    """Set of switched-on extras for the company, or whether one is on."""
    if company is None:
        return set() if code is None else False
    on = set(HRSettings.load(company).extras or []) & CODES
    return on if code is None else code in on


def save_extras(company, codes):
    settings = HRSettings.load(company)
    allowed = {code for code, _l1, _l2 in available(company)}
    settings.extras = sorted(set(codes) & allowed)
    settings.save(update_fields=["extras"])
    return settings.extras


# ------------------------------------------------------------------ WPS

def _qid(employee):
    doc = EmployeeDocument.objects.for_company(employee.company).filter(
        employee=employee, document_type="ID / residence card").first()
    return (doc.document_number if doc else "").strip()


def wps_file(company, payroll_run, now=None):
    """(file name, CSV text, problems). Problems name staff missing a QID, bank or IBAN — fix them and download again."""
    settings = HRSettings.load(company)
    now = timezone.localtime(now or timezone.now())
    period = payroll_run.period
    lines = list(PayrollLine.objects.for_company(company).filter(payroll_run=payroll_run).select_related("employee")
                 .order_by("employee__name"))
    problems = []
    if not settings.wps_employer_eid or not settings.wps_payer_bank or not settings.wps_payer_iban:
        problems.append(_("Fill the employer ID, bank and IBAN in HR settings."))
    period_days = (period.end_date - period.start_date).days + 1
    rows, total = [], ZERO
    for n, line in enumerate(lines, start=1):
        emp = line.employee
        qid = _qid(emp)
        missing = [label for value, label in ((qid, _("QID")), (emp.bank_short_name, _("bank")), (emp.iban, _("IBAN")))
                   if not value]
        if missing:
            problems.append(_("%(name)s: no %(what)s") % {"name": emp.name, "what": ", ".join(missing)})
        worked = max(Decimal("0"), Decimal(period_days) - (line.absence_days or ZERO))
        extra_income = (line.allowances or ZERO) + (line.overtime_amount or ZERO)
        deductions = (line.deductions or ZERO) + (line.absence_deduction or ZERO) + (line.advance_deduction or ZERO)
        rows.append([f"{n:06d}", qid, emp.visa_id, emp.name, emp.bank_short_name, emp.iban, "M", f"{worked:g}",
                     f"{line.net_pay:.2f}", f"{line.basic_pay:.2f}", f"{line.overtime_hours:g}", f"{extra_income:.2f}",
                     f"{deductions:.2f}", "Normal Payment", ""])
        total += line.net_pay
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["Employer EID", "File Creation Date", "File Creation Time", "Payer EID", "Payer QID",
                "Payer Bank Short Name", "Payer IBAN", "Salary Year and Month", "Total Salaries", "Total records",
                "SIF Version"])
    w.writerow([settings.wps_employer_eid, now.strftime("%Y%m%d"), now.strftime("%H%M"),
                settings.wps_payer_eid or settings.wps_employer_eid, settings.wps_payer_qid, settings.wps_payer_bank,
                settings.wps_payer_iban, period.start_date.strftime("%Y%m"), f"{total:.2f}", len(rows), "1"])
    w.writerow(["Record Sequence", "Employee QID", "Employee Visa ID", "Employee Name", "Employee Bank Short Name",
                "Employee Account", "Salary Frequency", "Number of Working days", "Net Salary", "Basic Salary",
                "Extra hours", "Extra income", "Deductions", "Payment Type", "Notes / Comments"])
    w.writerows(rows)
    name = f"SIF_{settings.wps_employer_eid or 'EMPLOYER'}_{settings.wps_payer_bank or 'BANK'}_{now:%Y%m%d}_{now:%H%M}.csv"
    return name, out.getvalue(), problems


# ------------------------------------------------------------------ gratuity & final settlement

def service_years(employee, last_day):
    if not employee.joined_date or last_day < employee.joined_date:
        return ZERO
    return (Decimal((last_day - employee.joined_date).days + 1) / Decimal("365")).quantize(CENT)


def _basic(employee):
    st = getattr(employee, "salary_structure", None)
    return st.basic_pay if st else (employee.salary or ZERO)


def gratuity(employee, last_day, settings=None):
    """Qatar labour law: at least 3 weeks' basic pay for each year of service, once a year is completed
    (days per year is set in HR settings); part years count pro rata. Day rate = basic ÷ 30."""
    settings = settings or HRSettings.load(employee.company)
    years = service_years(employee, last_day)
    if years < 1:
        return years, ZERO
    basic = _basic(employee)
    if employee.pay_basis == "daily":
        basic *= 30
    elif employee.pay_basis == "hourly":
        basic *= 8 * 30
    amount = (basic / Decimal("30") * settings.gratuity_days_per_year * years).quantize(CENT, ROUND_HALF_UP)
    return years, amount


def vacation_balance(employee, today=None, settings=None):
    """Leave days earned since joining less vacation days taken; months since the last ticket."""
    settings = settings or HRSettings.load(employee.company)
    today = today or timezone.localdate()
    years = service_years(employee, today)
    earned = (settings.vacation_days_per_year * years).quantize(Decimal("0.1"))
    taken = sum((Decimal(v.days) for v in employee.vacations.all()), ZERO)
    last_ticket = employee.vacations.filter(ticket_given=True).order_by("-start_date").first()
    since = last_ticket.start_date if last_ticket else employee.joined_date
    months = ((today.year - since.year) * 12 + today.month - since.month) if since else 0
    return {"earned": earned, "taken": taken, "balance": max(ZERO, earned - taken), "months_since_ticket": months,
            "ticket_due": bool(since) and months >= settings.ticket_every_months}


def _last_paid_day(employee):
    line = (PayrollLine.objects.for_company(employee.company).filter(employee=employee)
            .exclude(payroll_run__status="reversed").select_related("payroll_run__period")
            .order_by("-payroll_run__period__end_date").first())
    return line.payroll_run.period.end_date if line else None


def draft_settlement(employee, last_day, reason="resigned", other_additions=ZERO, other_deductions=ZERO,
                     ticket_amount=ZERO, notes=""):
    """Work out (not save) the settlement for someone leaving on last_day."""
    from .services import _money_total, employee_advance_balance
    if not employee.joined_date:
        raise ValidationError(_("Enter the joining date on the staff record first."))
    if last_day < employee.joined_date:
        raise ValidationError(_("The last day is before the joining date."))
    settings = HRSettings.load(employee.company)
    years, grat = gratuity(employee, last_day, settings)
    st = getattr(employee, "salary_structure", None)
    monthly = _basic(employee) + (_money_total(st.allowances) if st else ZERO)
    paid_to = _last_paid_day(employee)
    start = max(employee.joined_date, (paid_to + timedelta(days=1)) if paid_to else employee.joined_date)
    if employee.pay_basis in ("daily", "hourly"):
        from .services import worked_time
        days, hours = worked_time(company=employee.company, employee=employee, start=start, end=last_day)
        salary_days = days
        salary = _basic(employee) * (days if employee.pay_basis == "daily" else hours)
    else:
        salary_days = Decimal(max(0, (last_day - start).days + 1))
        salary = monthly / Decimal("30") * salary_days
    leave = vacation_balance(employee, last_day, settings)["balance"]
    leave_amount = _basic(employee) / Decimal("30") * leave if employee.pay_basis == "monthly" else ZERO
    advance = employee_advance_balance(company=employee.company, employee=employee)
    s = FinalSettlement(company=employee.company, employee=employee, last_day=last_day, reason=reason, years=years,
                        basic=_basic(employee), gratuity=grat, salary_days=salary_days,
                        salary_amount=salary.quantize(CENT), leave_days=leave, leave_amount=leave_amount.quantize(CENT),
                        ticket_amount=Decimal(ticket_amount or 0).quantize(CENT),
                        other_additions=Decimal(other_additions or 0).quantize(CENT),
                        advance_deduction=advance, other_deductions=Decimal(other_deductions or 0).quantize(CENT),
                        notes=notes)
    s.net = (s.gratuity + s.salary_amount + s.leave_amount + s.ticket_amount + s.other_additions
             - s.advance_deduction - s.other_deductions)
    return s


@transaction.atomic
def pay_settlement(settlement, user, method="cash"):
    """Record the payment: salary & benefits expense, advances cleared, cash / bank out; the person leaves."""
    from apps.accounting.models import Account
    from apps.accounting.services import post_journal_entry
    from .services import _cash_account
    s = FinalSettlement.objects.select_for_update().select_related("employee").get(pk=settlement.pk)
    if s.status == "paid":
        raise ValidationError(_("This settlement is already paid."))
    if s.net < 0:
        raise ValidationError(_("The deductions are more than the amount due."))
    company = s.company
    cash, advances = _cash_account(company, method)
    expense = Account.objects.for_company(company).get(code="5200")
    gross = s.net + s.advance_deduction
    lines = [(expense, gross, ZERO)]
    if s.net:
        lines.append((cash, ZERO, s.net))
    if s.advance_deduction:
        lines.append((advances, ZERO, s.advance_deduction))
    today = timezone.localdate()
    if gross:
        s.journal_entry = post_journal_entry(
            company=company, date=today, user=user, lines=lines, reference=f"EOS-{s.pk}",
            memo=f"Final settlement: {s.employee.name}", source_type="final_settlement", source_id=s.pk)
    remaining = s.advance_deduction
    for adv in SalaryAdvance.objects.for_company(company).filter(employee=s.employee).prefetch_related("recoveries"):
        take = min(adv.outstanding, remaining)
        if take > 0:
            AdvanceRecovery.objects.create(company=company, advance=adv, date=today, amount=take,
                                           source="bank" if method == "bank" else "cash")
            remaining -= take
    s.status, s.method, s.paid_at = "paid", method, timezone.now()
    s.save()
    emp = s.employee
    emp.is_active, emp.employment_status, emp.leaving_date = False, "terminated", s.last_day
    emp.save(update_fields=["is_active", "employment_status", "leaving_date"])
    return s


# ------------------------------------------------------------------ vacation

def add_vacation(employee, start, end, ticket_given=False, ticket_amount=ZERO, notes=""):
    if not start or not end or end < start:
        raise ValidationError(_("Choose the first day and the day back at work."))
    overlap = employee.vacations.filter(start_date__lte=end, end_date__gte=start).exists()
    if overlap:
        raise ValidationError(_("%(name)s already has a vacation in these dates.") % {"name": employee.name})
    return Vacation.objects.create(company=employee.company, employee=employee, start_date=start, end_date=end,
                                   ticket_given=bool(ticket_given), ticket_amount=Decimal(ticket_amount or 0),
                                   notes=(notes or "")[:255])


def vacation_board(company, today=None):
    """Away now, late back (end date passed, not returned), coming up (next 30 days), and staff due a ticket."""
    today = today or timezone.localdate()
    qs = Vacation.objects.for_company(company).select_related("employee")
    away = [v for v in qs.filter(start_date__lte=today, returned_on__isnull=True, end_date__gte=today)]
    late = [v for v in qs.filter(returned_on__isnull=True, end_date__lt=today)]
    for v in late:
        v.days_late = (today - v.end_date).days
    upcoming = list(qs.filter(start_date__gt=today, start_date__lte=today + timedelta(days=30)))
    settings = HRSettings.load(company)
    due = []
    for emp in Employee.objects.for_company(company).filter(is_active=True, joined_date__isnull=False).prefetch_related("vacations"):
        bal = vacation_balance(emp, today, settings)
        if bal["ticket_due"]:
            emp.balance = bal
            due.append(emp)
    return {"away": away, "late": late, "upcoming": upcoming, "due": due}


# ------------------------------------------------------------------ camps

def camps(company):
    """Active camps with residents, free beds and the monthly cost per head."""
    from django.db.models import Count, Q
    from .models import Camp
    rows = list(Camp.objects.for_company(company).filter(is_active=True).annotate(
        people=Count("residents", filter=Q(residents__is_active=True))))
    for camp in rows:
        camp.free = max(0, camp.capacity - camp.people) if camp.capacity else None
        camp.per_head = head_cost(camp, camp.people)
    return rows


def head_cost(camp, people=None):
    """A month's cost of one resident: their share of the camp, plus food and transport."""
    if camp is None:
        return ZERO
    if people is None:
        people = camp.residents.filter(is_active=True).count()
    share = (camp.monthly_cost / Decimal(people)) if people else ZERO
    return (share + camp.food_per_head + camp.transport_per_head).quantize(CENT)


def camp_costs(company):
    """{employee_id: monthly cost per head} for everyone living in a camp."""
    out = {}
    for camp in camps(company):
        for emp_id in camp.residents.filter(is_active=True).values_list("id", flat=True):
            out[emp_id] = camp.per_head
    return out


# ------------------------------------------------------------------ recruitment: visa quota and sub-agents

def visa_quotas(company, today=None):
    from apps.industry.models import VisaQuota
    from django.db.models import Count, Q
    today = today or timezone.localdate()
    rows = list(VisaQuota.objects.for_company(company).annotate(
        used=Count("placements", filter=~Q(placements__stage__in=["rejected", "withdrawn"]))))
    for q in rows:
        q.left = max(0, q.total - q.used)
        q.expired = bool(q.expiry_date and q.expiry_date < today)
        q.expiring = bool(q.expiry_date and not q.expired and q.expiry_date <= today + timedelta(days=30))
    return rows


def agent_statement(company):
    """Per sub-agent: candidates sent, joined, commission owed (on people who joined) and paid (agent costs)."""
    from apps.industry.models import Candidate, Placement, PlacementCost
    from apps.suppliers.models import Supplier
    from django.db.models import Sum
    agents = []
    for agent in Supplier.objects.for_company(company).filter(candidates__isnull=False).distinct().order_by("name"):
        placements = Placement.objects.for_company(company).filter(candidate__agent=agent).select_related(
            "candidate", "job_order")
        joined = [p for p in placements if p.stage == "deployed"]
        owed = sum((p.agent_commission for p in joined), ZERO)
        paid = PlacementCost.objects.for_company(company).filter(
            placement__candidate__agent=agent, cost_type="agent").aggregate(s=Sum("amount"))["s"] or ZERO
        agents.append({"agent": agent, "sent": Candidate.objects.for_company(company).filter(agent=agent).count(),
                       "joined": joined, "owed": owed, "paid": paid, "balance": owed - paid})
    return agents
