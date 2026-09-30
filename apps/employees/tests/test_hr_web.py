from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.accounting.models import JournalLine
from apps.employees import services as hr
from apps.employees.models import (AdvanceRecovery, Attendance, Employee, HRSettings, LeaveType, PayrollLine,
                                   PayrollRun, SalaryAdvance, SalaryStructure)
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def staff(company, name="Ravi", basic="3000", allowance="600", deduction="0"):
    employee = Employee.objects.create(company=company, name=name, salary=Decimal(basic))
    SalaryStructure.objects.create(company=company, employee=employee, basic_pay=Decimal(basic),
                                   allowances={"Allowances": allowance} if allowance else {},
                                   deductions={"Deductions": deduction} if deduction != "0" else {})
    return employee


def balance(company, code):
    rows = JournalLine.objects.filter(journal_entry__company=company, account__code=code)
    return sum((r.debit - r.credit for r in rows), Decimal("0"))


def test_advance_is_recovered_in_instalments_through_payroll(tenant_a, tenant_a_owner):
    ravi = staff(tenant_a)
    advance = hr.give_advance(company=tenant_a, user=tenant_a_owner, employee=ravi, amount="1000",
                              monthly_deduction="400", date=date(2026, 8, 20), method="cash")
    assert balance(tenant_a, "1300") == Decimal("1000") and balance(tenant_a, "1000") == Decimal("-1000")
    for month, expected in (("2026-09", "400"), ("2026-10", "400"), ("2026-11", "200"), ("2026-12", "0")):
        period = hr.month_period(tenant_a, month)
        run = hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
        line = run.lines.get()
        assert line.advance_deduction == Decimal(expected)
        assert line.net_pay == Decimal("3600") - Decimal(expected)
        hr.post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    advance.refresh_from_db()
    assert advance.outstanding == 0 and balance(tenant_a, "1300") == 0
    # the payroll journal balances with the advance credit
    assert JournalLine.objects.filter(journal_entry__company=tenant_a, journal_entry__source_type="payroll").count() > 0
    assert balance(tenant_a, "5200") == Decimal("14400")


def test_reversing_payroll_restores_the_advance(tenant_a, tenant_a_owner):
    ravi = staff(tenant_a)
    advance = hr.give_advance(company=tenant_a, user=tenant_a_owner, employee=ravi, amount="500", date=date(2026, 9, 2))
    period = hr.month_period(tenant_a, "2026-09")
    run = hr.post_payroll(company=tenant_a, user=tenant_a_owner, date=period.end_date,
                          payroll_run=hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period))
    assert advance.outstanding == 0
    hr.reverse_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=date(2026, 10, 1))
    advance = SalaryAdvance.objects.get(pk=advance.pk)
    assert advance.outstanding == Decimal("500") and not AdvanceRecovery.objects.exists()
    assert balance(tenant_a, "1300") == Decimal("500")


def test_advance_never_makes_net_pay_negative_and_can_be_repaid_in_cash(tenant_a, tenant_a_owner):
    small = staff(tenant_a, name="Small", basic="800", allowance="")
    advance = hr.give_advance(company=tenant_a, user=tenant_a_owner, employee=small, amount="2000", date=date(2026, 9, 1))
    run = hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=hr.month_period(tenant_a, "2026-09"))
    assert run.lines.get().advance_deduction == Decimal("800") and run.lines.get().net_pay == 0
    hr.repay_advance(company=tenant_a, user=tenant_a_owner, advance=advance, amount="300", date=date(2026, 9, 5))
    assert SalaryAdvance.objects.get(pk=advance.pk).outstanding == Decimal("1700")
    with pytest.raises(ValidationError):
        hr.repay_advance(company=tenant_a, user=tenant_a_owner, advance=advance, amount="5000", date=date(2026, 9, 5))
    with pytest.raises(ValidationError):
        hr.give_advance(company=tenant_a, user=tenant_a_owner, employee=small, amount="100", monthly_deduction="200",
                        date=date(2026, 9, 1))


def test_absence_and_unpaid_leave_reduce_gross_pay(tenant_a, tenant_a_owner):
    ravi = staff(tenant_a, basic="3000", allowance="0")
    for day, status in ((1, "absent"), (2, "absent"), (3, "half_day"), (4, "present")):
        hr.record_attendance(company=tenant_a, employee=ravi, date=date(2026, 9, day), status=status)
    unpaid = LeaveType.objects.create(company=tenant_a, name="Unpaid", paid=False, annual_entitlement=30)
    leave = hr.request_leave(company=tenant_a, employee=ravi, leave_type=unpaid,
                             start_date=date(2026, 9, 28), end_date=date(2026, 10, 2))
    hr.review_leave(company=tenant_a, request=leave, reviewer=tenant_a_owner, approve=True)
    # weekly off Sat/Sun (no country) -> 28, 29, 30 Sep are working days = 3 unpaid days in September
    run = hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=hr.month_period(tenant_a, "2026-09"))
    line = run.lines.get()
    assert line.absence_days == Decimal("5.5")
    assert line.absence_deduction == Decimal("550.00")  # 3000 / 30 days x 5.5
    assert line.gross_pay == Decimal("2450.00")
    HRSettings.objects.filter(company=tenant_a).update(deduct_absence=False)
    hr.delete_draft_run(company=tenant_a, payroll_run=run)
    run = hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=hr.month_period(tenant_a, "2026-09"))
    assert run.lines.get().gross_pay == Decimal("3000")


def test_gulf_weekly_off_is_friday(tenant_a):
    tenant_a.country = "Qatar"
    tenant_a.save(update_fields=["country"])
    # Thu 24 Sep - Sat 26 Sep 2026: Friday is off -> 2 days
    assert hr.leave_days(company=tenant_a, start_date=date(2026, 9, 24), end_date=date(2026, 9, 26)) == Decimal("2")


def test_paying_salary_moves_money_from_payroll_payable(tenant_a, tenant_a_owner):
    ravi = staff(tenant_a)
    period = hr.month_period(tenant_a, "2026-09")
    run = hr.create_payroll_run(company=tenant_a, user=tenant_a_owner, period=period)
    line = run.lines.get()
    with pytest.raises(ValidationError):
        hr.pay_payslip(company=tenant_a, user=tenant_a_owner, payroll_line=line)
    hr.post_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=period.end_date)
    hr.pay_payslip(company=tenant_a, user=tenant_a_owner, payroll_line=line, method="bank", date=period.end_date)
    line.refresh_from_db()
    assert line.payment_status == "paid" and line.payment_method == "bank"
    assert balance(tenant_a, "2200") == 0 and balance(tenant_a, "1010") == Decimal("-3600")
    with pytest.raises(ValidationError):
        hr.pay_payslip(company=tenant_a, user=tenant_a_owner, payroll_line=line)
    with pytest.raises(ValidationError):
        hr.reverse_payroll(company=tenant_a, user=tenant_a_owner, payroll_run=run, date=date(2026, 10, 1))


def signup(client, code, email):
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "", "password": "Staff-Pages-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email)


@pytest.mark.parametrize("code", ["restaurant", "supermarket", "jewelry_shop", "gym", "saloon", "construction"])
def test_staff_and_hr_pages_for_every_kind_of_business(client, code, settings):
    settings.SIGNUP_LIMIT_PER_IP_PER_HOUR = 1000
    call_command("seed_platform")
    signup(client, code, f"hr-{code}@test.qa")
    home = client.get(reverse("webapp:staff_list"))
    assert home.status_code == 200 and reverse("webapp:hr_payroll").encode() in home.content
    for name in ("hr_attendance", "hr_attendance_month", "hr_leave", "hr_advances", "hr_payroll", "hr_documents",
                 "hr_settings", "staff_add"):
        assert client.get(reverse(f"webapp:{name}")).status_code == 200, name


def test_full_staff_flow_through_the_web(client, settings):
    settings.SIGNUP_LIMIT_PER_IP_PER_HOUR = 1000
    call_command("seed_platform")
    company = signup(client, "restaurant", "flow@test.qa")
    response = client.post(reverse("webapp:staff_add"), {
        "name": "Anil", "phone": "97455501234", "role_title": "Chef", "joined_date": "2026-01-10",
        "employment_status": "active", "user": "", "basic_pay": "3100", "allowance": "500", "deduction": "",
        "overtime_rate": "15"})
    anil = Employee.objects.get(company=company, name="Anil")
    assert response.status_code == 302 and anil.salary_structure.basic_pay == Decimal("3100")
    assert client.get(reverse("webapp:staff_detail", args=[anil.id])).status_code == 200

    client.post(reverse("webapp:hr_attendance"), {"date": "2026-09-03", f"s_{anil.id}": "absent"})
    assert Attendance.objects.get(employee=anil).status == "absent"
    client.post(reverse("webapp:hr_advances"), {"employee": anil.id, "amount": "900", "monthly_deduction": "300",
                                                "date": "2026-09-01", "method": "cash", "reason": "Family"})
    assert SalaryAdvance.objects.get(employee=anil).monthly_deduction == Decimal("300")

    payroll_url = reverse("webapp:hr_payroll") + "?m=2026-09"
    client.post(reverse("webapp:hr_payroll"), {"m": "2026-09", "action": "create"})
    line = PayrollLine.objects.get(employee=anil)
    assert line.advance_deduction == Decimal("300") and line.absence_deduction == Decimal("120.00")
    assert line.net_pay == Decimal("3100") + 500 - Decimal("120") - 300
    client.post(reverse("webapp:hr_payroll"), {"m": "2026-09", "action": "post"})
    client.post(reverse("webapp:hr_payroll"), {"m": "2026-09", "action": "pay", "method": "cash"})
    line.refresh_from_db()
    assert PayrollRun.objects.get(company=company).status == "posted" and line.payment_status == "paid"
    page = client.get(payroll_url).content.decode()
    assert "Anil" in page
    slip = client.get(reverse("webapp:hr_payslip", args=[line.id])).content.decode()
    assert "wa.me/97455501234" in slip and "3180.00" in slip

    # removing someone with salary history keeps them as former staff
    client.post(reverse("webapp:staff_delete", args=[anil.id]))
    anil.refresh_from_db()
    assert not anil.is_active and anil.employment_status == "terminated"
