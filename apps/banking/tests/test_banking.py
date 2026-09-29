"""
Phase 29 — Bank and Cash Management + Reconciliation.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def _get_account(company, code):
    from apps.accounting.models import Account
    return Account.objects.for_company(company).get(code=code)


def _make_bank_account(company, code="1010", **kwargs):
    from apps.banking.models import BankAccount
    return BankAccount.objects.create(
        company=company, name=kwargs.pop("name", "Main Bank"),
        account_type=kwargs.pop("account_type", "bank"),
        ledger_account=_get_account(company, code), **kwargs,
    )


class TestDepositWithdrawalTransfer:
    def test_deposit_debits_bank_and_credits_contra(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import account_balance
        from apps.banking.services import record_deposit

        bank = _make_bank_account(tenant_a)
        revenue = _get_account(tenant_a, "4000")

        record_deposit(
            company=tenant_a, bank_account=bank, contra_account=revenue,
            amount=Decimal("500.00"), date="2026-01-10", user=tenant_a_owner,
        )
        assert account_balance(bank.ledger_account) == Decimal("500.00")
        assert account_balance(revenue) == Decimal("500.00")

    def test_withdrawal_credits_bank_and_debits_contra(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import account_balance
        from apps.banking.services import record_deposit, record_withdrawal

        bank = _make_bank_account(tenant_a)
        revenue = _get_account(tenant_a, "4000")
        expense = _get_account(tenant_a, "5100")

        record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                        amount=Decimal("500.00"), date="2026-01-10", user=tenant_a_owner)
        record_withdrawal(company=tenant_a, bank_account=bank, contra_account=expense,
                           amount=Decimal("120.00"), date="2026-01-15", user=tenant_a_owner)

        assert account_balance(bank.ledger_account) == Decimal("380.00")
        assert account_balance(expense) == Decimal("120.00")

    def test_transfer_moves_money_between_own_accounts_without_touching_profit(self, tenant_a, tenant_a_owner):
        from apps.accounting.services import account_balance, profit_and_loss
        from apps.banking.services import record_deposit, transfer_between_accounts

        bank = _make_bank_account(tenant_a, code="1010", name="Bank")
        cash = _make_bank_account(tenant_a, code="1000", name="Cash", account_type="cash")
        revenue = _get_account(tenant_a, "4000")

        record_deposit(company=tenant_a, bank_account=cash, contra_account=revenue,
                        amount=Decimal("1000.00"), date="2026-01-01", user=tenant_a_owner)
        profit_before = profit_and_loss(tenant_a)["net_profit"]

        transfer_between_accounts(
            company=tenant_a, from_account=cash, to_account=bank,
            amount=Decimal("300.00"), date="2026-01-05", user=tenant_a_owner,
        )

        assert account_balance(cash.ledger_account) == Decimal("700.00")
        assert account_balance(bank.ledger_account) == Decimal("300.00")
        profit_after = profit_and_loss(tenant_a)["net_profit"]
        assert profit_after == profit_before  # acceptance criteria: transfer does not affect profit

    def test_transfer_rejects_cross_tenant_account(self, tenant_a, tenant_b, tenant_a_owner):
        from apps.banking.services import transfer_between_accounts

        bank_a = _make_bank_account(tenant_a, code="1010")
        bank_b = _make_bank_account(tenant_b, code="1010")

        with pytest.raises(ValidationError, match="active company"):
            transfer_between_accounts(
                company=tenant_a, from_account=bank_a, to_account=bank_b,
                amount=Decimal("10.00"), date="2026-01-01", user=tenant_a_owner,
            )

    def test_transfer_rejects_same_account(self, tenant_a, tenant_a_owner):
        from apps.banking.services import transfer_between_accounts

        bank = _make_bank_account(tenant_a)
        with pytest.raises(ValidationError, match="itself"):
            transfer_between_accounts(
                company=tenant_a, from_account=bank, to_account=bank,
                amount=Decimal("10.00"), date="2026-01-01", user=tenant_a_owner,
            )


CSV_SAMPLE = """date,description,amount,reference
2026-01-05,Customer payment,500.00,INV-1
2026-01-07,Office rent,-200.00,RENT-JAN
"""


class TestStatementImport:
    def test_import_creates_transactions(self, tenant_a, tenant_a_owner):
        from apps.banking.models import StatementTransaction
        from apps.banking.services import import_statement_csv

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(
            company=tenant_a, bank_account=bank, file_name="jan.csv",
            csv_text=CSV_SAMPLE, user=tenant_a_owner,
        )
        assert batch.row_count == 2
        assert batch.skipped_duplicate_count == 0
        rows = StatementTransaction.objects.filter(bank_account=bank)
        assert rows.count() == 2
        assert all(r.status == "unmatched" for r in rows)

    def test_duplicate_whole_file_import_is_rejected(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv

        bank = _make_bank_account(tenant_a)
        import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                              csv_text=CSV_SAMPLE, user=tenant_a_owner)
        with pytest.raises(ValidationError, match="already been imported"):
            import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan-again.csv",
                                  csv_text=CSV_SAMPLE, user=tenant_a_owner)

    def test_overlapping_rows_across_different_files_are_skipped_not_duplicated(self, tenant_a, tenant_a_owner):
        from apps.banking.models import StatementTransaction
        from apps.banking.services import import_statement_csv

        bank = _make_bank_account(tenant_a)
        import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                              csv_text=CSV_SAMPLE, user=tenant_a_owner)

        overlapping_csv = CSV_SAMPLE + "2026-01-10,New transaction,50.00,REF-3\n"
        batch2 = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan-updated.csv",
                                       csv_text=overlapping_csv, user=tenant_a_owner)

        assert batch2.row_count == 3
        assert batch2.skipped_duplicate_count == 2
        assert StatementTransaction.objects.filter(bank_account=bank).count() == 3

    def test_missing_required_column_is_rejected(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv

        bank = _make_bank_account(tenant_a)
        with pytest.raises(ValidationError, match="missing required column"):
            import_statement_csv(company=tenant_a, bank_account=bank, file_name="bad.csv",
                                  csv_text="date,amount\n2026-01-01,10\n", user=tenant_a_owner)


class TestMatching:
    def test_match_requires_exact_amount(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit, match_transaction

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))

        revenue = _get_account(tenant_a, "4000")
        wrong_entry = record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                                      amount=Decimal("499.00"), date="2026-01-05", user=tenant_a_owner)

        with pytest.raises(ValidationError, match="does not match"):
            match_transaction(company=tenant_a, statement_transaction=deposit_row, journal_entry=wrong_entry, user=tenant_a_owner)

    def test_match_and_unmatch_round_trip(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit, match_transaction, unmatch_transaction

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))
        revenue = _get_account(tenant_a, "4000")
        entry = record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                                amount=Decimal("500.00"), date="2026-01-05", user=tenant_a_owner)

        match_transaction(company=tenant_a, statement_transaction=deposit_row, journal_entry=entry, user=tenant_a_owner)
        deposit_row.refresh_from_db()
        assert deposit_row.status == "matched"

        unmatch_transaction(company=tenant_a, statement_transaction=deposit_row, user=tenant_a_owner)
        deposit_row.refresh_from_db()
        assert deposit_row.status == "unmatched"
        assert deposit_row.matched_journal_entry_id is None

        # Idempotent
        unmatch_transaction(company=tenant_a, statement_transaction=deposit_row, user=tenant_a_owner)

    def test_cannot_rematch_an_already_matched_row(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit, match_transaction

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))
        revenue = _get_account(tenant_a, "4000")
        entry = record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                                amount=Decimal("500.00"), date="2026-01-05", user=tenant_a_owner)
        match_transaction(company=tenant_a, statement_transaction=deposit_row, journal_entry=entry, user=tenant_a_owner)

        entry2 = record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                                 amount=Decimal("500.00"), date="2026-01-06", user=tenant_a_owner)
        with pytest.raises(ValidationError, match="already matched"):
            match_transaction(company=tenant_a, statement_transaction=deposit_row, journal_entry=entry2, user=tenant_a_owner)

    def test_deposit_with_statement_transaction_auto_matches(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))
        revenue = _get_account(tenant_a, "4000")

        record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                        amount=Decimal("500.00"), date="2026-01-05", user=tenant_a_owner,
                        statement_transaction=deposit_row)

        deposit_row.refresh_from_db()
        assert deposit_row.status == "matched"

    def test_suggest_matches_finds_same_amount_entry_without_changing_state(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit, suggest_matches

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))
        revenue = _get_account(tenant_a, "4000")
        entry = record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                                amount=Decimal("500.00"), date="2026-01-06", user=tenant_a_owner)

        suggestions = suggest_matches(company=tenant_a, statement_transaction=deposit_row)
        assert entry in suggestions

        deposit_row.refresh_from_db()
        assert deposit_row.status == "unmatched"  # suggestions never auto-confirm


class TestReconciliation:
    def test_difference_reaches_zero_once_fully_matched(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, record_deposit, record_withdrawal, reconciliation_summary

        bank = _make_bank_account(tenant_a)
        batch = import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                                      csv_text=CSV_SAMPLE, user=tenant_a_owner)
        deposit_row = batch.transactions.get(amount=Decimal("500.00"))
        withdrawal_row = batch.transactions.get(amount=Decimal("-200.00"))

        revenue = _get_account(tenant_a, "4000")
        expense = _get_account(tenant_a, "5100")

        record_deposit(company=tenant_a, bank_account=bank, contra_account=revenue,
                        amount=Decimal("500.00"), date="2026-01-05", user=tenant_a_owner,
                        statement_transaction=deposit_row)
        record_withdrawal(company=tenant_a, bank_account=bank, contra_account=expense,
                           amount=Decimal("200.00"), date="2026-01-07", user=tenant_a_owner,
                           statement_transaction=withdrawal_row)

        summary = reconciliation_summary(company=tenant_a, bank_account=bank)
        assert summary["difference"] == Decimal("0")
        assert summary["unmatched_count"] == 0
        assert summary["matched_count"] == 2

    def test_difference_nonzero_when_ledger_entry_missing(self, tenant_a, tenant_a_owner):
        from apps.banking.services import import_statement_csv, reconciliation_summary

        bank = _make_bank_account(tenant_a)
        import_statement_csv(company=tenant_a, bank_account=bank, file_name="jan.csv",
                              csv_text=CSV_SAMPLE, user=tenant_a_owner)

        summary = reconciliation_summary(company=tenant_a, bank_account=bank)
        # Statement shows +500-200=300 of activity but nothing posted to the ledger yet.
        assert summary["difference"] == Decimal("-300.00")
        assert summary["unmatched_count"] == 2


class TestBankingApi:
    def test_owner_can_create_bank_account_and_deposit(self, tenant_a, as_tenant_a_owner):
        ledger_account = _get_account(tenant_a, "1010")
        resp = as_tenant_a_owner.post("/api/banking/bank-accounts/", {
            "name": "Main Bank", "account_type": "bank", "ledger_account": ledger_account.id,
        })
        assert resp.status_code == 201, resp.data
        bank_id = resp.data["id"]

        revenue = _get_account(tenant_a, "4000")
        resp = as_tenant_a_owner.post(f"/api/banking/bank-accounts/{bank_id}/deposit/", {
            "contra_account": revenue.id, "amount": "250.00", "date": "2026-01-01",
        })
        assert resp.status_code == 201, resp.data

    def test_staff_cannot_access_banking(self, tenant_a, member_factory):
        from conftest import jwt_client

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)
        resp = client.get("/api/banking/bank-accounts/")
        assert resp.status_code == 403

    def test_cross_tenant_bank_account_is_404(self, tenant_a, tenant_b, as_tenant_a_owner):
        bank_b = _make_bank_account(tenant_b, code="1010")
        resp = as_tenant_a_owner.get(f"/api/banking/bank-accounts/{bank_b.id}/reconciliation/")
        assert resp.status_code == 404

    def test_ledger_account_must_belong_to_company(self, tenant_a, tenant_b, as_tenant_a_owner):
        foreign_account = _get_account(tenant_b, "1010")
        resp = as_tenant_a_owner.post("/api/banking/bank-accounts/", {
            "name": "Sneaky", "account_type": "bank", "ledger_account": foreign_account.id,
        })
        assert resp.status_code == 400
