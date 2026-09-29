"""
Phase 28 — Fiscal Years, Period Locking and Year-End Close.

Mirrors the style of test_ledger_integrity.py: tests hit the ledger/
service layer directly (not just derived report numbers), plus API-level
tests for RBAC and tenant isolation on the new FiscalYearViewSet actions.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def _get_account(company, code):
    from apps.accounting.models import Account
    return Account.objects.for_company(company).get(code=code)


def _make_fiscal_year(company, start, end, **kwargs):
    from apps.accounting.models import FiscalYear
    return FiscalYear.objects.create(company=company, start_date=start, end_date=end, **kwargs)


def _post(company, user, date, lines, **kwargs):
    from apps.accounting.services import post_journal_entry
    return post_journal_entry(company=company, date=date, user=user, lines=lines, **kwargs)


class TestPeriodLocking:
    def test_posting_allowed_when_no_fiscal_year_configured(self, tenant_a, tenant_a_owner):
        """Backward compatibility: companies/dates with no FiscalYear row
        behave exactly as before this phase."""
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        entry = _post(
            tenant_a, tenant_a_owner, "2026-01-01",
            [(cash, Decimal("50.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("50.00"))],
        )
        assert entry.id is not None

    def test_posting_blocked_in_closed_fiscal_year(self, tenant_a, tenant_a_owner):
        _make_fiscal_year(tenant_a, "2025-01-01", "2025-12-31", is_closed=True)
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        with pytest.raises(ValidationError, match="is closed"):
            _post(
                tenant_a, tenant_a_owner, "2025-06-15",
                [(cash, Decimal("10.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("10.00"))],
            )

    def test_posting_blocked_on_or_before_lock_date(self, tenant_a, tenant_a_owner):
        _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31", lock_date="2026-06-30")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        with pytest.raises(ValidationError, match="locked"):
            _post(
                tenant_a, tenant_a_owner, "2026-06-30",
                [(cash, Decimal("10.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("10.00"))],
            )

    def test_posting_allowed_after_lock_date(self, tenant_a, tenant_a_owner):
        _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31", lock_date="2026-06-30")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        entry = _post(
            tenant_a, tenant_a_owner, "2026-07-01",
            [(cash, Decimal("10.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("10.00"))],
        )
        assert entry.id is not None

    def test_override_lock_bypasses_both_checks(self, tenant_a, tenant_a_owner):
        _make_fiscal_year(tenant_a, "2025-01-01", "2025-12-31", is_closed=True, lock_date="2025-12-31")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        entry = _post(
            tenant_a, tenant_a_owner, "2025-06-15",
            [(cash, Decimal("10.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("10.00"))],
            override_lock=True,
        )
        assert entry.id is not None

    def test_lock_only_applies_to_the_fiscal_year_that_covers_the_date(self, tenant_a, tenant_a_owner):
        """A closed 2025 must not block posting into 2026."""
        _make_fiscal_year(tenant_a, "2025-01-01", "2025-12-31", is_closed=True)
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        entry = _post(
            tenant_a, tenant_a_owner, "2026-01-15",
            [(cash, Decimal("10.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("10.00"))],
        )
        assert entry.id is not None


class TestYearEndClose:
    def test_close_zeroes_income_and_expense_and_credits_retained_earnings(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year, account_balance

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        expense = _get_account(tenant_a, "5100")

        _post(tenant_a, tenant_a_owner, "2026-03-01",
              [(cash, Decimal("1000.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("1000.00"))])
        _post(tenant_a, tenant_a_owner, "2026-04-01",
              [(expense, Decimal("400.00"), Decimal("0")), (cash, Decimal("0"), Decimal("400.00"))])

        entry = close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        fy.refresh_from_db()

        assert fy.is_closed is True
        assert fy.closed_by_id == tenant_a_owner.id
        assert entry is not None

        # Income/expense zeroed for the closed period...
        assert account_balance(revenue, as_of="2026-12-31") == Decimal("0")
        assert account_balance(expense, as_of="2026-12-31") == Decimal("0")
        # ...and the 1000 - 400 = 600 profit landed in Retained Earnings.
        retained_earnings = _get_account(tenant_a, "3900")
        assert account_balance(retained_earnings) == Decimal("600.00")

    def test_close_with_a_loss_debits_retained_earnings(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year, account_balance

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        expense = _get_account(tenant_a, "5100")

        _post(tenant_a, tenant_a_owner, "2026-03-01",
              [(cash, Decimal("200.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("200.00"))])
        _post(tenant_a, tenant_a_owner, "2026-04-01",
              [(expense, Decimal("500.00"), Decimal("0")), (cash, Decimal("0"), Decimal("500.00"))])

        close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)

        retained_earnings = _get_account(tenant_a, "3900")
        assert account_balance(retained_earnings) == Decimal("-300.00")

    def test_close_is_idempotent(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year
        from apps.accounting.models import JournalEntry

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        _post(tenant_a, tenant_a_owner, "2026-03-01",
              [(cash, Decimal("100.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("100.00"))])

        first = close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        second = close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)

        assert first.id == second.id
        count = JournalEntry.objects.filter(
            company=tenant_a, source_type="fiscal_year_close", source_id=fy.id
        ).count()
        assert count == 1

    def test_close_with_no_activity_marks_closed_without_a_journal_entry(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        entry = close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        fy.refresh_from_db()
        assert fy.is_closed is True
        assert entry is None

    def test_close_rejects_fiscal_year_from_another_company(self, tenant_a, tenant_b, tenant_b_owner):
        from apps.accounting.services import close_fiscal_year

        fy_b = _make_fiscal_year(tenant_b, "2026-01-01", "2026-12-31")
        with pytest.raises(ValidationError, match="does not belong"):
            close_fiscal_year(company=tenant_a, fiscal_year=fy_b, user=tenant_b_owner)


class TestReopen:
    def test_reopen_sets_is_closed_false_and_is_idempotent(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year, reopen_fiscal_year

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)

        reopen_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        fy.refresh_from_db()
        assert fy.is_closed is False

        # Idempotent — reopening an already-open year is a safe no-op.
        reopen_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        fy.refresh_from_db()
        assert fy.is_closed is False

    def test_reopen_logs_an_audit_entry(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import close_fiscal_year, reopen_fiscal_year
        from apps.audit.models import AuditLog

        fy = _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")
        close_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)
        reopen_fiscal_year(company=tenant_a, fiscal_year=fy, user=tenant_a_owner)

        assert AuditLog.objects.filter(
            company=tenant_a, action="reopen_fiscal_year", object_id=str(fy.id)
        ).exists()


class TestBalanceSheetSeparatesRetainedEarnings:
    def test_closed_year_profit_moves_into_equity_and_current_year_shown_separately(
        self, tenant_a, tenant_a_owner
    ):
        from apps.accounting.services import close_fiscal_year, balance_sheet

        fy_2025 = _make_fiscal_year(tenant_a, "2025-01-01", "2025-12-31")
        _make_fiscal_year(tenant_a, "2026-01-01", "2026-12-31")

        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")

        # 2025: 500 profit, closed.
        _post(tenant_a, tenant_a_owner, "2025-06-01",
              [(cash, Decimal("500.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("500.00"))])
        close_fiscal_year(company=tenant_a, fiscal_year=fy_2025, user=tenant_a_owner)

        # 2026: 120 profit so far, still open.
        _post(tenant_a, tenant_a_owner, "2026-02-01",
              [(cash, Decimal("120.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("120.00"))])

        sheet = balance_sheet(tenant_a, as_of="2026-06-30")

        # Prior year's 500 now lives permanently in the Equity section...
        assert sheet["total_equity"] >= Decimal("500.00")
        # ...and is not re-added on top via "retained_earnings", which is
        # only this year's not-yet-closed 120.
        assert sheet["retained_earnings"] == Decimal("120.00")


class TestFiscalYearApi:
    def test_owner_can_create_and_close(self, tenant_a, as_tenant_a_owner):
        resp = as_tenant_a_owner.post("/api/accounting/fiscal-years/", {
            "start_date": "2026-01-01", "end_date": "2026-12-31",
        })
        assert resp.status_code == 201, resp.data
        fy_id = resp.data["id"]

        resp = as_tenant_a_owner.post(f"/api/accounting/fiscal-years/{fy_id}/close/")
        assert resp.status_code == 200, resp.data
        assert resp.data["fiscal_year"]["is_closed"] is True

    def test_accountant_can_close_but_not_reopen(self, tenant_a, member_factory):
        from conftest import jwt_client

        accountant = member_factory(tenant_a, "Accountant")
        client = jwt_client(accountant)

        resp = client.post("/api/accounting/fiscal-years/", {
            "start_date": "2026-01-01", "end_date": "2026-12-31",
        })
        assert resp.status_code == 201, resp.data
        fy_id = resp.data["id"]

        resp = client.post(f"/api/accounting/fiscal-years/{fy_id}/close/")
        assert resp.status_code == 200, resp.data

        resp = client.post(f"/api/accounting/fiscal-years/{fy_id}/reopen/")
        assert resp.status_code == 403

    def test_staff_cannot_create_fiscal_years(self, tenant_a, member_factory):
        from conftest import jwt_client

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        resp = client.post("/api/accounting/fiscal-years/", {
            "start_date": "2026-01-01", "end_date": "2026-12-31",
        })
        assert resp.status_code == 403

    def test_cross_tenant_fiscal_year_close_is_404(self, tenant_a, tenant_b, as_tenant_a_owner):
        fy_b = _make_fiscal_year(tenant_b, "2026-01-01", "2026-12-31")
        resp = as_tenant_a_owner.post(f"/api/accounting/fiscal-years/{fy_b.id}/close/")
        assert resp.status_code == 404
