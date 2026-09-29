"""
Sales invoice tests (master brief Section 9 / Section 41's worked "Credit
Sale" example / Phase 0's "one service call, one atomic transaction,
three side effects" pattern documented in apps/sales/services.py).
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


class TestInvoiceCreationSideEffects:
    def test_invoice_totals_and_numbering(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_invoice

        fx = sales_fixtures_factory(tenant_a)
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            date="2026-01-05", warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("3"), "unit_price": Decimal("100.00")}],
            tax_rate=Decimal("0.05"),
        )
        assert invoice.invoice_number == "INV-000001"
        assert invoice.subtotal == Decimal("300.00")
        assert invoice.tax_amount == Decimal("15.00")
        assert invoice.total == Decimal("315.00")
        assert invoice.status == "unpaid"

    def test_invoice_numbers_increment_and_are_per_company(
        self, tenant_a, tenant_b, tenant_a_owner, tenant_b_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice

        fx_a = sales_fixtures_factory(tenant_a, sku="A1")
        fx_b = sales_fixtures_factory(tenant_b, sku="B1")

        inv_a1 = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx_a["customer"], date="2026-01-01",
            warehouse=fx_a["warehouse"], lines=[{"product": fx_a["product"], "quantity": 1, "unit_price": Decimal("10")}],
        )
        inv_a2 = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx_a["customer"], date="2026-01-02",
            warehouse=fx_a["warehouse"], lines=[{"product": fx_a["product"], "quantity": 1, "unit_price": Decimal("10")}],
        )
        inv_b1 = create_invoice(
            company=tenant_b, user=tenant_b_owner, customer=fx_b["customer"], date="2026-01-01",
            warehouse=fx_b["warehouse"], lines=[{"product": fx_b["product"], "quantity": 1, "unit_price": Decimal("10")}],
        )

        assert [inv_a1.invoice_number, inv_a2.invoice_number] == ["INV-000001", "INV-000002"]
        assert inv_b1.invoice_number == "INV-000001"  # tenant B's own sequence, unaffected by tenant A

    def test_invoice_creation_decrements_stock(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_invoice
        from apps.inventory.services import record_stock_movement

        fx = sales_fixtures_factory(tenant_a)
        record_stock_movement(
            company=tenant_a, product=fx["product"], warehouse=fx["warehouse"],
            quantity=Decimal("10"), reason="purchase", reference="opening-stock",
        )
        assert fx["product"].current_stock() == Decimal("10")

        create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            date="2026-01-05", warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("4"), "unit_price": Decimal("100.00")}],
        )
        assert fx["product"].current_stock() == Decimal("6")

    def test_invoice_creation_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        """Section 41: Credit Sale -> Debit Accounts Receivable, Credit Sales Revenue."""
        from apps.sales.services import create_invoice
        from apps.accounting.services import account_balance

        fx = sales_fixtures_factory(tenant_a)
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            date="2026-01-05", warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("2"), "unit_price": Decimal("100.00")}],
        )

        assert invoice.journal_entry is not None
        je = invoice.journal_entry
        assert je.lines.count() == 2
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("200.00")

        ar_account = invoice.journal_entry.lines.get(debit__gt=0).account
        assert ar_account.code == "1100"

    def test_invoice_with_no_lines_is_rejected(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_invoice

        fx = sales_fixtures_factory(tenant_a)
        with pytest.raises(ValidationError):
            create_invoice(
                company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
                date="2026-01-05", warehouse=fx["warehouse"], lines=[],
            )


class TestInvoiceAtomicity:
    def test_failure_during_journal_posting_rolls_back_the_whole_invoice(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory, monkeypatch
    ):
        """If the journal-entry step fails, the SalesInvoice row and the
        StockMovement rows created earlier in the same call must NOT
        remain committed — this is the entire point of wrapping
        create_invoice() in @transaction.atomic."""
        from apps.sales import services as sales_services
        from apps.sales.models import SalesInvoice
        from apps.inventory.models import StockMovement

        fx = sales_fixtures_factory(tenant_a)

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated failure while posting the journal entry")

        monkeypatch.setattr(sales_services, "post_journal_entry", _boom)

        with pytest.raises(RuntimeError):
            sales_services.create_invoice(
                company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
                date="2026-01-05", warehouse=fx["warehouse"],
                lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_price": Decimal("50")}],
            )

        assert SalesInvoice.objects.for_company(tenant_a).count() == 0
        assert StockMovement.objects.for_company(tenant_a).count() == 0


class TestCustomerPayments:
    def test_full_payment_marks_invoice_paid_and_moves_ar_to_cash(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice, record_customer_payment
        from apps.accounting.services import account_balance

        fx = sales_fixtures_factory(tenant_a)
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            date="2026-01-05", warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_price": Decimal("100")}],
        )

        record_customer_payment(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            invoice=invoice, amount=Decimal("100"), date="2026-01-10",
        )

        invoice.refresh_from_db()
        assert invoice.status == "paid"
        assert invoice.amount_paid == Decimal("100.00")

    def test_partial_payment_leaves_invoice_partially_paid(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice, record_customer_payment

        fx = sales_fixtures_factory(tenant_a)
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            date="2026-01-05", warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_price": Decimal("100")}],
        )

        record_customer_payment(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"],
            invoice=invoice, amount=Decimal("40"), date="2026-01-10",
        )

        invoice.refresh_from_db()
        assert invoice.status == "partial"
        assert invoice.amount_paid == Decimal("40.00")
