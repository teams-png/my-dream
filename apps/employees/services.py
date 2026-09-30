from decimal import Decimal
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.utils import timezone

from .models import (Commission, Attendance, Holiday, LeaveBalance, LeaveRequest,
                     EmployeeDocument, DocumentAlertLog, SalaryStructure,
                     OvertimeEntry, PayrollRun, PayrollLine, HRSettings, SalaryAdvance, AdvanceRecovery)

CENT = Decimal("0.01")


def record_commission(*, company, employee, reference_type, reference_id, amount, date):
    """
    The one sanctioned way to create a Commission row — call this from any
    vertical (spa, saloon, beauty parlour, ...) instead of writing to
    Commission directly, so every vertical's commission logic stays
    consistent and reportable from one place.
    """
    return Commission.objects.create(
        company=company, employee=employee, reference_type=reference_type,
        reference_id=reference_id, amount=amount, date=date,
    )


def leave_days(*, company, start_date, end_date):
    if end_date < start_date:
        raise ValidationError("Leave end date cannot be before start date.")
    holidays = set(Holiday.objects.for_company(company).filter(
        date__range=(start_date, end_date)
    ).values_list("date", flat=True))
    off_days = set(HRSettings.load(company).weekly_off_days or [])
    total = Decimal("0")
    current = start_date
    while current <= end_date:
        if current.weekday() not in off_days and current not in holidays:
            total += 1
        current += timedelta(days=1)
    return total


@transaction.atomic
def request_leave(*, company, employee, leave_type, start_date, end_date, reason=""):
    if employee.company_id != company.id or leave_type.company_id != company.id:
        raise ValidationError("Employee and leave type must belong to the active company.")
    days = leave_days(company=company, start_date=start_date, end_date=end_date)
    balance, _ = LeaveBalance.objects.get_or_create(
        company=company, employee=employee, leave_type=leave_type, year=start_date.year,
        defaults={"opening": leave_type.annual_entitlement},
    )
    pending = LeaveRequest.objects.for_company(company).filter(
        employee=employee, leave_type=leave_type, status="pending", start_date__year=start_date.year
    ).aggregate(total=models.Sum("days"))["total"] or Decimal("0")
    if days <= 0 or balance.available - pending < days:
        raise ValidationError("Insufficient leave balance.")
    return LeaveRequest.objects.create(
        company=company, employee=employee, leave_type=leave_type,
        start_date=start_date, end_date=end_date, days=days, reason=reason,
    )


@transaction.atomic
def review_leave(*, company, request, reviewer, approve):
    request = LeaveRequest.objects.select_for_update().get(pk=request.pk, company=company)
    if request.status != "pending":
        raise ValidationError("Only pending leave requests can be reviewed.")
    if approve:
        balance = LeaveBalance.objects.select_for_update().get(
            company=company, employee=request.employee, leave_type=request.leave_type,
            year=request.start_date.year,
        )
        if balance.available < request.days:
            raise ValidationError("Insufficient leave balance.")
        balance.used += request.days
        balance.save(update_fields=["used"])
        request.status = "approved"
    else:
        request.status = "rejected"
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return request


def record_attendance(*, company, employee, date, status, check_in=None, check_out=None, notes=""):
    if employee.company_id != company.id:
        raise ValidationError("Employee does not belong to the active company.")
    obj, _ = Attendance.objects.update_or_create(
        company=company, employee=employee, date=date,
        defaults={"status": status, "check_in": check_in, "check_out": check_out, "notes": notes},
    )
    return obj


def check_document_expiry_and_notify(*, company, today=None, thresholds=(30, 7, 0)):
    from apps.notifications.services import notify
    today = today or timezone.localdate()
    created = 0
    for document in EmployeeDocument.objects.for_company(company).filter(expiry_date__isnull=False).select_related("employee"):
        days = (document.expiry_date - today).days
        applicable = [threshold for threshold in thresholds if days <= threshold]
        if not applicable:
            continue
        threshold = min(applicable)
        if not DocumentAlertLog.objects.for_company(company).filter(
                document=document, threshold_days=threshold).exists():
            notify(company=company, notif_type="employee_document_expiry",
                   title=f"{document.document_type} expiry: {document.employee.name}",
                   message=f"Expiry date: {document.expiry_date}.")
            DocumentAlertLog.objects.create(company=company, document=document, threshold_days=threshold)
            created += 1
    return created


def _money_total(values):
    try:
        return sum((Decimal(str(value)) for value in (values or {}).values()), Decimal("0"))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError("Allowance and deduction values must be valid numbers.")


@transaction.atomic
def submit_overtime(*, company, employee, date, hours, overtime_type="normal", multiplier=1, notes=""):
    if employee.company_id != company.id:
        raise ValidationError("Employee does not belong to the active company.")
    if Decimal(str(hours)) <= 0 or Decimal(str(multiplier)) <= 0:
        raise ValidationError("Overtime hours and multiplier must be greater than zero.")
    return OvertimeEntry.objects.create(
        company=company, employee=employee, date=date, hours=hours,
        overtime_type=overtime_type, multiplier=multiplier, notes=notes,
    )


@transaction.atomic
def review_overtime(*, company, overtime, reviewer, approve):
    overtime = OvertimeEntry.objects.select_for_update().get(pk=overtime.pk, company=company)
    if overtime.status != "pending":
        raise ValidationError("Only pending overtime can be reviewed.")
    overtime.status = "approved" if approve else "rejected"
    overtime.approved_by = reviewer
    overtime.approved_at = timezone.now()
    overtime.save(update_fields=["status", "approved_by", "approved_at"])
    return overtime


@transaction.atomic
def create_payroll_run(*, company, user, period):
    if period.company_id != company.id:
        raise ValidationError("Payroll period does not belong to the active company.")
    if period.end_date < period.start_date:
        raise ValidationError("Payroll period end date cannot be before its start date.")
    if PayrollRun.objects.for_company(company).filter(period=period).exists():
        raise ValidationError("A payroll run already exists for this period.")

    payroll_run = PayrollRun.objects.create(company=company, period=period, created_by=user)
    structures = SalaryStructure.objects.for_company(company).filter(
        is_active=True, employee__is_active=True,
    ).select_related("employee")
    total_gross = total_deductions = total_net = total_advances = Decimal("0")
    settings = HRSettings.load(company)
    period_days = Decimal((period.end_date - period.start_date).days + 1)
    for structure in structures:
        approved_overtime = OvertimeEntry.objects.for_company(company).filter(
            employee=structure.employee, status="approved",
            date__range=(period.start_date, period.end_date),
        )
        overtime_hours = sum((row.hours for row in approved_overtime), Decimal("0"))
        overtime_amount = sum(
            (row.hours * structure.overtime_hourly_rate * row.multiplier for row in approved_overtime),
            Decimal("0"),
        )
        allowances = _money_total(structure.allowances)
        deductions = _money_total(structure.deductions)
        absence_days = absence_deduction = Decimal("0")
        if settings.deduct_absence:
            absence_days = unpaid_absence_days(company=company, employee=structure.employee,
                                               start=period.start_date, end=period.end_date)
            if absence_days:
                daily = (structure.basic_pay + allowances) / period_days
                absence_deduction = min((daily * absence_days).quantize(CENT), structure.basic_pay + allowances)
        gross = structure.basic_pay + allowances + overtime_amount - absence_deduction
        net = gross - deductions
        if net < 0:
            raise ValidationError(f"Net pay cannot be negative for {structure.employee.name}.")
        advance = min(advance_due(company=company, employee=structure.employee), net)
        net -= advance
        PayrollLine.objects.create(
            company=company, payroll_run=payroll_run, employee=structure.employee,
            basic_pay=structure.basic_pay, allowances=allowances,
            overtime_hours=overtime_hours, overtime_amount=overtime_amount,
            deductions=deductions, gross_pay=gross, net_pay=net,
            absence_days=absence_days, absence_deduction=absence_deduction, advance_deduction=advance,
        )
        total_gross += gross
        total_deductions += deductions
        total_net += net
        total_advances += advance
    payroll_run.total_gross = total_gross
    payroll_run.total_deductions = total_deductions
    payroll_run.total_net = total_net
    payroll_run.total_advances = total_advances
    payroll_run.save(update_fields=["total_gross", "total_deductions", "total_net", "total_advances"])
    return payroll_run


@transaction.atomic
def post_payroll(*, company, user, payroll_run, date):
    from apps.accounting.models import Account
    from apps.accounting.services import post_journal_entry, seed_chart_of_accounts
    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk, company=company)
    if payroll_run.status != "draft":
        raise ValidationError("Only a draft payroll run can be posted.")
    if not payroll_run.lines.exists() or payroll_run.total_gross <= 0:
        raise ValidationError("Payroll run has no payable lines.")
    seed_chart_of_accounts(company)
    expense = Account.objects.for_company(company).get(code="5200")
    payable = Account.objects.for_company(company).get(code="2200")
    deduction_payable = Account.objects.for_company(company).get(code="2250")
    lines = [(expense, payroll_run.total_gross, Decimal("0")),
             (payable, Decimal("0"), payroll_run.total_net)]
    if payroll_run.total_deductions:
        lines.append((deduction_payable, Decimal("0"), payroll_run.total_deductions))
    if payroll_run.total_advances:
        lines.append((Account.objects.for_company(company).get(code="1300"), Decimal("0"), payroll_run.total_advances))
        _record_payroll_recoveries(company=company, payroll_run=payroll_run, date=date)
    entry = post_journal_entry(
        company=company, date=date, lines=lines, user=user,
        reference=f"PAYROLL-{payroll_run.id}", memo=f"Payroll: {payroll_run.period.name}",
        source_type="payroll", source_id=payroll_run.id,
    )
    payroll_run.status = "posted"
    payroll_run.posted_by = user
    payroll_run.posted_at = timezone.now()
    payroll_run.journal_entry = entry
    payroll_run.save(update_fields=["status", "posted_by", "posted_at", "journal_entry"])
    return payroll_run


@transaction.atomic
def reverse_payroll(*, company, user, payroll_run, date):
    from apps.accounting.models import Account
    from apps.accounting.services import post_journal_entry, seed_chart_of_accounts
    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk, company=company)
    if payroll_run.status != "posted":
        raise ValidationError("Only a posted payroll run can be reversed.")
    if payroll_run.lines.filter(payment_status="paid").exists():
        raise ValidationError("A payroll run with paid payslips cannot be reversed.")
    seed_chart_of_accounts(company)
    expense = Account.objects.for_company(company).get(code="5200")
    payable = Account.objects.for_company(company).get(code="2200")
    deduction_payable = Account.objects.for_company(company).get(code="2250")
    lines = [(payable, payroll_run.total_net, Decimal("0")),
             (expense, Decimal("0"), payroll_run.total_gross)]
    if payroll_run.total_deductions:
        lines.insert(1, (deduction_payable, payroll_run.total_deductions, Decimal("0")))
    if payroll_run.total_advances:
        lines.insert(1, (Account.objects.for_company(company).get(code="1300"), payroll_run.total_advances, Decimal("0")))
        AdvanceRecovery.objects.for_company(company).filter(payroll_line__payroll_run=payroll_run).delete()
    entry = post_journal_entry(
        company=company, date=date, lines=lines, user=user,
        reference=f"PAYROLL-REV-{payroll_run.id}", memo=f"Payroll reversal: {payroll_run.period.name}",
        source_type="payroll_reversal", source_id=payroll_run.id,
    )
    payroll_run.status = "reversed"
    payroll_run.reversal_journal_entry = entry
    payroll_run.save(update_fields=["status", "reversal_journal_entry"])
    return payroll_run


@transaction.atomic
def mark_payroll_paid(*, company, payroll_line):
    payroll_line = PayrollLine.objects.select_for_update().select_related("payroll_run").get(
        pk=payroll_line.pk, company=company,
    )
    if payroll_line.payroll_run.status != "posted":
        raise ValidationError("Only posted payroll payslips can be marked paid.")
    if payroll_line.payment_status == "paid":
        return payroll_line
    payroll_line.payment_status = "paid"
    payroll_line.paid_at = timezone.now()
    payroll_line.save(update_fields=["payment_status", "paid_at"])
    return payroll_line


# ---------------------------------------------------------------------------
# Absence, salary advances, month payroll and salary payment (web HR screens)
# ---------------------------------------------------------------------------

def unpaid_absence_days(*, company, employee, start, end):
    """Absent = 1 day, half day = 0.5, plus approved leave of unpaid leave types in the period."""
    days = Decimal("0")
    for status in Attendance.objects.for_company(company).filter(
            employee=employee, date__range=(start, end), status__in=["absent", "half_day"]).values_list("status", flat=True):
        days += Decimal("1") if status == "absent" else Decimal("0.5")
    for leave in LeaveRequest.objects.for_company(company).filter(
            employee=employee, status="approved", leave_type__paid=False, start_date__lte=end, end_date__gte=start):
        days += leave_days(company=company, start_date=max(leave.start_date, start), end_date=min(leave.end_date, end))
    return days


def advance_due(*, company, employee):
    """The instalment to recover on the next payslip across all open advances (oldest first)."""
    total = Decimal("0")
    for advance in SalaryAdvance.objects.for_company(company).filter(employee=employee).prefetch_related("recoveries"):
        outstanding = advance.outstanding
        if outstanding > 0:
            total += min(advance.monthly_deduction, outstanding)
    return total


def employee_advance_balance(*, company, employee):
    return sum((a.outstanding for a in SalaryAdvance.objects.for_company(company).filter(employee=employee)
                .prefetch_related("recoveries")), Decimal("0"))


def _record_payroll_recoveries(*, company, payroll_run, date):
    for line in payroll_run.lines.filter(advance_deduction__gt=0).select_related("employee"):
        remaining = line.advance_deduction
        for advance in (SalaryAdvance.objects.for_company(company).filter(employee=line.employee)
                        .order_by("date", "id").prefetch_related("recoveries")):
            if remaining <= 0:
                break
            take = min(advance.outstanding, remaining)
            if take > 0:
                AdvanceRecovery.objects.create(company=company, advance=advance, payroll_line=line,
                                               date=date, amount=take, source="payroll")
                remaining -= take


def _cash_account(company, method):
    from apps.accounting.models import Account
    from apps.accounting.services import seed_chart_of_accounts
    seed_chart_of_accounts(company)
    return (Account.objects.for_company(company).get(code="1010" if method == "bank" else "1000"),
            Account.objects.for_company(company).get(code="1300"))


@transaction.atomic
def give_advance(*, company, user, employee, amount, date, monthly_deduction=None, method="cash", reason=""):
    from apps.accounting.services import post_journal_entry
    if employee.company_id != company.id:
        raise ValidationError("Employee does not belong to the active company.")
    amount = Decimal(str(amount)).quantize(CENT)
    if amount <= 0:
        raise ValidationError("The advance must be more than zero.")
    monthly = Decimal(str(monthly_deduction)).quantize(CENT) if monthly_deduction not in (None, "") else amount
    if monthly <= 0 or monthly > amount:
        raise ValidationError("The monthly deduction must be more than zero and not more than the advance.")
    cash, advances = _cash_account(company, method)
    advance = SalaryAdvance.objects.create(company=company, employee=employee, date=date, amount=amount,
                                           monthly_deduction=monthly, method=method, reason=reason, given_by=user)
    advance.journal_entry = post_journal_entry(
        company=company, date=date, user=user, lines=[(advances, amount, Decimal("0")), (cash, Decimal("0"), amount)],
        reference=f"ADV-{advance.id}", memo=f"Salary advance: {employee.name}", source_type="salary_advance", source_id=advance.id)
    advance.save(update_fields=["journal_entry"])
    return advance


@transaction.atomic
def repay_advance(*, company, user, advance, amount, date, method="cash"):
    """The staff member pays (part of) an advance back directly instead of through salary."""
    from apps.accounting.services import post_journal_entry
    advance = SalaryAdvance.objects.select_for_update().get(pk=advance.pk, company=company)
    amount = Decimal(str(amount)).quantize(CENT)
    if amount <= 0 or amount > advance.outstanding:
        raise ValidationError("Enter an amount up to the balance of the advance.")
    cash, advances = _cash_account(company, method)
    recovery = AdvanceRecovery.objects.create(company=company, advance=advance, date=date, amount=amount,
                                              source="bank" if method == "bank" else "cash")
    recovery.journal_entry = post_journal_entry(
        company=company, date=date, user=user, lines=[(cash, amount, Decimal("0")), (advances, Decimal("0"), amount)],
        reference=f"ADV-REP-{recovery.id}", memo=f"Advance repaid: {advance.employee.name}",
        source_type="salary_advance_repayment", source_id=recovery.id)
    recovery.save(update_fields=["journal_entry"])
    return recovery


def ensure_salary_structures(company):
    """Staff with a salary but no structure (added before the HR screens) get a basic one."""
    from .models import Employee
    for employee in Employee.objects.for_company(company).filter(is_active=True, salary__gt=0, salary_structure__isnull=True):
        SalaryStructure.objects.create(company=company, employee=employee, basic_pay=employee.salary)


def month_period(company, key):
    """PayrollPeriod for 'YYYY-MM'."""
    import calendar
    from datetime import date as _date
    from .models import PayrollPeriod
    year, month = (int(part) for part in key.split("-"))
    start = _date(year, month, 1)
    end = _date(year, month, calendar.monthrange(year, month)[1])
    period, _ = PayrollPeriod.objects.get_or_create(company=company, start_date=start, end_date=end,
                                                    defaults={"name": start.strftime("%B %Y")})
    return period


@transaction.atomic
def delete_draft_run(*, company, payroll_run):
    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk, company=company)
    if payroll_run.status != "draft":
        raise ValidationError("Only a draft payroll can be recalculated.")
    payroll_run.delete()


@transaction.atomic
def pay_payslip(*, company, user, payroll_line, method="cash", date=None):
    """Pays the net salary: moves it from Payroll Payable to cash or bank and marks the payslip paid."""
    from apps.accounting.models import Account
    from apps.accounting.services import post_journal_entry
    date = date or timezone.localdate()
    payroll_line = PayrollLine.objects.select_for_update().select_related("payroll_run", "employee").get(
        pk=payroll_line.pk, company=company)
    if payroll_line.payroll_run.status != "posted":
        raise ValidationError("Approve (post) the payroll before paying salaries.")
    if payroll_line.payment_status == "paid":
        raise ValidationError("This salary is already paid.")
    if payroll_line.net_pay > 0:
        cash, _ = _cash_account(company, method)
        payable = Account.objects.for_company(company).get(code="2200")
        post_journal_entry(
            company=company, date=date, user=user, lines=[(payable, payroll_line.net_pay, Decimal("0")),
                                                          (cash, Decimal("0"), payroll_line.net_pay)],
            reference=f"SAL-{payroll_line.id}", memo=f"Salary paid: {payroll_line.employee.name} ({payroll_line.payroll_run.period.name})",
            source_type="salary_payment", source_id=payroll_line.id)
    payroll_line.payment_status = "paid"
    payroll_line.paid_at = timezone.now()
    payroll_line.payment_method = method
    payroll_line.save(update_fields=["payment_status", "paid_at", "payment_method"])
    return payroll_line
