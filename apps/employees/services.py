from decimal import Decimal
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.utils import timezone

from .models import (Commission, Attendance, Holiday, LeaveBalance, LeaveRequest,
                     EmployeeDocument, DocumentAlertLog, SalaryStructure,
                     OvertimeEntry, PayrollRun, PayrollLine)


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
    total = Decimal("0")
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
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
    total_gross = total_deductions = total_net = Decimal("0")
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
        gross = structure.basic_pay + allowances + overtime_amount
        net = gross - deductions
        if net < 0:
            raise ValidationError(f"Net pay cannot be negative for {structure.employee.name}.")
        PayrollLine.objects.create(
            company=company, payroll_run=payroll_run, employee=structure.employee,
            basic_pay=structure.basic_pay, allowances=allowances,
            overtime_hours=overtime_hours, overtime_amount=overtime_amount,
            deductions=deductions, gross_pay=gross, net_pay=net,
        )
        total_gross += gross
        total_deductions += deductions
        total_net += net
    payroll_run.total_gross = total_gross
    payroll_run.total_deductions = total_deductions
    payroll_run.total_net = total_net
    payroll_run.save(update_fields=["total_gross", "total_deductions", "total_net"])
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
