from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.employees.models import Employee, SalaryStructure, PayrollPeriod, OvertimeEntry
from apps.employees.services import (submit_overtime, review_overtime, create_payroll_run,
                                     post_payroll, reverse_payroll, mark_payroll_paid)

pytestmark = pytest.mark.django_db


def payroll_setup(company):
    employee = Employee.objects.create(company=company, name="Payroll Employee")
    SalaryStructure.objects.create(
        company=company, employee=employee, basic_pay=Decimal("1000"),
        allowances={"housing": "200", "transport": 50}, deductions={"tax": "100"},
        overtime_hourly_rate=Decimal("10"),
    )
    period = PayrollPeriod.objects.create(
        company=company, name="September 2026", start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    )
    return employee, period


def test_payroll_uses_only_approved_overtime(tenant_a, tenant_a_owner):
    employee, period = payroll_setup(tenant_a)
    approved = submit_overtime(company=tenant_a, employee=employee, date=date(2026, 9, 10),
                               hours=2, overtime_type="normal", multiplier=Decimal("1.5"))
    review_overtime(company=tenant_a, overtime=approved, reviewer=tenant_a_owner, approve=True)
    submit_overtime(company=tenant_a, employee=employee, date=date(2026, 9, 11),
                    hours=5, overtime_type="normal", multiplier=2)
    run = create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    line = run.lines.get()
    assert line.overtime_hours == Decimal("2")
    assert line.overtime_amount == Decimal("30")
    assert line.gross_pay == Decimal("1280")
    assert line.net_pay == Decimal("1180")
    assert run.journal_entry is None


def test_duplicate_payroll_period_is_blocked(tenant_a, tenant_a_owner):
    _, period = payroll_setup(tenant_a)
    create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    with pytest.raises(ValidationError, match="already exists"):
        create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)


def test_posted_payroll_creates_balanced_accounting_entry(tenant_a, tenant_a_owner):
    _, period = payroll_setup(tenant_a)
    run = create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    run = post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    debits = sum((line.debit for line in run.journal_entry.lines.all()), Decimal("0"))
    credits = sum((line.credit for line in run.journal_entry.lines.all()), Decimal("0"))
    assert run.status == "posted"
    assert debits == credits == run.total_gross
    assert run.total_gross == run.total_net + run.total_deductions


def test_payslip_payment_state_requires_posting(tenant_a, tenant_a_owner):
    _, period = payroll_setup(tenant_a)
    run = create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    line = run.lines.get()
    with pytest.raises(ValidationError, match="posted"):
        mark_payroll_paid(company=tenant_a, payroll_line=line)
    post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    line = mark_payroll_paid(company=tenant_a, payroll_line=line)
    assert line.payment_status == "paid"
    assert line.paid_at is not None


def test_unpaid_posted_payroll_can_be_reversed_once(tenant_a, tenant_a_owner):
    _, period = payroll_setup(tenant_a)
    run = create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    run = post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    run = reverse_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=date(2026, 10, 1))
    assert run.status == "reversed"
    assert run.reversal_journal_entry_id is not None
    with pytest.raises(ValidationError, match="posted"):
        reverse_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=date(2026, 10, 1))


def test_paid_payroll_cannot_be_reversed(tenant_a, tenant_a_owner):
    _, period = payroll_setup(tenant_a)
    run = create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    run = post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    mark_payroll_paid(company=tenant_a, payroll_line=run.lines.get())
    with pytest.raises(ValidationError, match="paid payslips"):
        reverse_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=date(2026, 10, 1))
