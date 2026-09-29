"""Phase 1 Section 38: 'User permissions' — Section 7's Owner/Accountant/Staff boundaries."""
import pytest

from apps.tenants.services import invite_member

pytestmark = pytest.mark.django_db


def test_staff_cannot_view_audit_logs(make_company, with_active_company):
    """Section 7: Staff should not see company-wide activity, only Owner should (Section 24)."""
    from tests.conftest import make_user

    company, owner = make_company("textile", owner_email="owner-staff-test@example.com")
    staff_user = make_user("staffmember@example.com")
    invite_member(company=company, user=staff_user, role_name="Staff")

    client = with_active_company(staff_user, company)
    resp = client.get("/api/audit/logs/")
    assert resp.status_code == 403


def test_owner_can_view_audit_logs(make_company, with_active_company):
    company, owner = make_company("textile", owner_email="owner-audit-test@example.com")
    client = with_active_company(owner, company)
    resp = client.get("/api/audit/logs/")
    assert resp.status_code == 200


def test_accountant_can_view_audit_logs_is_false_too(make_company, with_active_company):
    """Owner-only really means Owner-only — Accountant is not an exception (Section 24: 'completely separate')."""
    from tests.conftest import make_user

    company, owner = make_company("textile", owner_email="owner-acct-test@example.com")
    accountant = make_user("accountant1@example.com")
    invite_member(company=company, user=accountant, role_name="Accountant")

    client = with_active_company(accountant, company)
    resp = client.get("/api/audit/logs/")
    assert resp.status_code == 403
