from datetime import date, timedelta, time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.employees.models import (Employee, WorkShift, Attendance, LeaveType, LeaveBalance,
                                   Holiday, EmployeeDocument)
from apps.employees.services import (request_leave, review_leave, record_attendance,
                                     check_document_expiry_and_notify)
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_attendance_is_unique_and_update_safe(tenant_a):
    employee = Employee.objects.create(company=tenant_a, name="A")
    record_attendance(company=tenant_a, employee=employee, date=date.today(), status="present", check_in=time(8))
    record_attendance(company=tenant_a, employee=employee, date=date.today(), status="present", check_in=time(9))
    assert Attendance.objects.for_company(tenant_a).count() == 1
    assert Attendance.objects.for_company(tenant_a).get().check_in == time(9)


def test_leave_balance_excludes_weekend_and_holiday(tenant_a, tenant_a_owner):
    employee = Employee.objects.create(company=tenant_a, name="B")
    leave_type = LeaveType.objects.create(company=tenant_a, name="Annual", annual_entitlement=10)
    # 2026-09-21 Monday through Friday; Wednesday is a holiday => 4 days.
    Holiday.objects.create(company=tenant_a, name="Holiday", date=date(2026, 9, 23))
    request = request_leave(company=tenant_a, employee=employee, leave_type=leave_type,
                            start_date=date(2026, 9, 21), end_date=date(2026, 9, 25))
    assert request.days == Decimal("4")
    review_leave(company=tenant_a, request=request, reviewer=tenant_a_owner, approve=True)
    balance = LeaveBalance.objects.get(company=tenant_a, employee=employee, leave_type=leave_type, year=2026)
    assert balance.used == Decimal("4")
    assert balance.available == Decimal("6")


def test_insufficient_leave_is_blocked(tenant_a):
    employee = Employee.objects.create(company=tenant_a, name="C")
    leave_type = LeaveType.objects.create(company=tenant_a, name="Short", annual_entitlement=1)
    with pytest.raises(ValidationError, match="Insufficient"):
        request_leave(company=tenant_a, employee=employee, leave_type=leave_type,
                      start_date=date(2026, 9, 21), end_date=date(2026, 9, 23))


def test_document_expiry_notifications_are_deduplicated(tenant_a):
    employee = Employee.objects.create(company=tenant_a, name="D")
    EmployeeDocument.objects.create(company=tenant_a, employee=employee, document_type="Passport",
                                    expiry_date=date.today() + timedelta(days=7))
    assert check_document_expiry_and_notify(company=tenant_a, today=date.today()) == 1
    assert check_document_expiry_and_notify(company=tenant_a, today=date.today()) == 0
    assert Notification.objects.filter(company=tenant_a, notif_type="employee_document_expiry").count() == 1
