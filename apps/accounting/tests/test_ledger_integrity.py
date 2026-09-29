"""
Accounting integrity tests (master brief Section 8 / Section 41):
"Do not create a fake/simple accounting system... use proper double-entry
accounting principles." Every one of these tests checks the ledger
itself, not a derived number — a bug that makes P&L "look right" while
the underlying journal is unbalanced is exactly what this file guards
against.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def _get_account(company, code):
    from apps.accounting.models import Account
    return Account.objects.for_company(company).get(code=code)


class TestChartOfAccountsSeeding:
    def test_default_chart_of_accounts_is_seeded_on_company_creation(self, tenant_a):
        from apps.accounting.models import Account
        from apps.accounting.services import DEFAULT_CHART_OF_ACCOUNTS

        codes = set(Account.objects.for_company(tenant_a).values_list("code", flat=True))
        assert codes == {code for code, *_ in DEFAULT_CHART_OF_ACCOUNTS}


class TestJournalEntryBalance:
    def test_unbalanced_entry_is_rejected(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import post_journal_entry

        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")

        with pytest.raises(ValidationError, match="does not balance"):
            post_journal_entry(
                company=tenant_a, date="2026-01-01", user=tenant_a_owner,
                lines=[(cash, Decimal("100.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("90.00"))],
            )

    def test_zero_amount_entry_is_rejected(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import post_journal_entry

        cash = _get_account(tenant_a, "1000")
        with pytest.raises(ValidationError, match="no amount"):
            post_journal_entry(
                company=tenant_a, date="2026-01-01", user=tenant_a_owner,
                lines=[(cash, Decimal("0"), Decimal("0"))],
            )

    def test_rejected_entry_leaves_no_partial_rows(self, tenant_a, tenant_a_owner):
        """The whole point of wrapping post_journal_entry in a transaction:
        a rejected/failed entry must not leave a JournalEntry with only
        some of its JournalLines, or an entry with no lines at all."""
        from apps.accounting.models import JournalEntry
        from apps.accounting.services import post_journal_entry

        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")
        before = JournalEntry.objects.for_company(tenant_a).count()

        with pytest.raises(ValidationError):
            post_journal_entry(
                company=tenant_a, date="2026-01-01", user=tenant_a_owner,
                lines=[(cash, Decimal("100.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("90.00"))],
            )

        assert JournalEntry.objects.for_company(tenant_a).count() == before

    def test_balanced_cash_sale_entry_posts_correctly(self, tenant_a, tenant_a_owner):
        """Section 41 worked example: Cash Sale -> Debit Cash, Credit Sales Revenue."""
        from apps.accounting.services import post_journal_entry, account_balance

        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")

        post_journal_entry(
            company=tenant_a, date="2026-01-01", user=tenant_a_owner,
            lines=[(cash, Decimal("500.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("500.00"))],
        )

        assert account_balance(cash) == Decimal("500.00")
        assert account_balance(revenue) == Decimal("500.00")


class TestTrialBalanceAlwaysBalances:
    def test_trial_balance_debits_equal_credits_after_multiple_entries(self, tenant_a, tenant_a_owner):
        """The fundamental double-entry invariant: sum of every account's
        signed balance across the whole ledger must always net to zero,
        no matter how many entries have been posted."""
        from apps.accounting.services import post_journal_entry, trial_balance

        cash = _get_account(tenant_a, "1000")
        ar = _get_account(tenant_a, "1100")
        revenue = _get_account(tenant_a, "4000")
        expense = _get_account(tenant_a, "5100")

        # Cash sale
        post_journal_entry(
            company=tenant_a, date="2026-01-01", user=tenant_a_owner,
            lines=[(cash, Decimal("300"), Decimal("0")), (revenue, Decimal("0"), Decimal("300"))],
        )
        # Credit sale
        post_journal_entry(
            company=tenant_a, date="2026-01-02", user=tenant_a_owner,
            lines=[(ar, Decimal("150"), Decimal("0")), (revenue, Decimal("0"), Decimal("150"))],
        )
        # Expense paid from cash
        post_journal_entry(
            company=tenant_a, date="2026-01-03", user=tenant_a_owner,
            lines=[(expense, Decimal("80"), Decimal("0")), (cash, Decimal("0"), Decimal("80"))],
        )

        rows = trial_balance(tenant_a)
        net = sum(
            (balance if account.type in ("asset", "expense") else -balance)
            for account, balance in rows
        )
        assert net == Decimal("0")

    def test_profit_and_loss_matches_ledger_not_a_separate_calculation(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import post_journal_entry, profit_and_loss

        revenue = _get_account(tenant_a, "4000")
        cash = _get_account(tenant_a, "1000")
        expense = _get_account(tenant_a, "5100")

        post_journal_entry(
            company=tenant_a, date="2026-01-01", user=tenant_a_owner,
            lines=[(cash, Decimal("1000"), Decimal("0")), (revenue, Decimal("0"), Decimal("1000"))],
        )
        post_journal_entry(
            company=tenant_a, date="2026-01-02", user=tenant_a_owner,
            lines=[(expense, Decimal("400"), Decimal("0")), (cash, Decimal("0"), Decimal("400"))],
        )

        pl = profit_and_loss(tenant_a)
        assert pl["total_income"] == Decimal("1000")
        assert pl["total_expense"] == Decimal("400")
        assert pl["net_profit"] == Decimal("600")

    def test_voided_entry_excluded_from_balances(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import post_journal_entry, account_balance

        cash = _get_account(tenant_a, "1000")
        revenue = _get_account(tenant_a, "4000")

        entry = post_journal_entry(
            company=tenant_a, date="2026-01-01", user=tenant_a_owner,
            lines=[(cash, Decimal("200"), Decimal("0")), (revenue, Decimal("0"), Decimal("200"))],
        )
        entry.is_void = True
        entry.save(update_fields=["is_void"])

        assert account_balance(cash) == Decimal("0")
        assert account_balance(revenue) == Decimal("0")
