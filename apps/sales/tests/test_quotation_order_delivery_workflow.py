"""
Phase 33 — Sales Quotation → Sales Order → Delivery → Invoice Workflow.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def _make_order(company, user, customer, fixtures, quantity=Decimal("100"), unit_price=Decimal("10.00"), date="2026-01-01"):
    from apps.sales.services import create_sales_order
    return create_sales_order(
        company=company, user=user, customer=customer, date=date,
        lines=[{"product": fixtures["product"], "quantity": quantity, "unit_price": unit_price}],
    )


class TestQuotationAndOrderNoLedgerImpact:
    def test_creating_a_quotation_posts_no_journal_entry(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.accounting.models import JournalEntry
        from apps.sales.services import create_quotation

        fixtures = sales_fixtures_factory(tenant_a)
        before = JournalEntry.objects.for_company(tenant_a).count()
        create_quotation(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-01",
            lines=[{"product": fixtures["product"], "quantity": Decimal("5"), "unit_price": Decimal("20.00")}],
        )
        after = JournalEntry.objects.for_company(tenant_a).count()
        assert after == before

    def test_creating_a_sales_order_posts_no_journal_entry_and_no_stock_movement(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.accounting.models import JournalEntry

        fixtures = sales_fixtures_factory(tenant_a)
        before_je = JournalEntry.objects.for_company(tenant_a).count()
        _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures)
        after_je = JournalEntry.objects.for_company(tenant_a).count()
        assert after_je == before_je
        assert fixtures["product"].current_stock() == 0

    def test_quotation_to_order_preserves_quoted_price(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_quotation, accept_quotation, create_sales_order

        fixtures = sales_fixtures_factory(tenant_a)
        quotation = create_quotation(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-01",
            lines=[{"product": fixtures["product"], "quantity": Decimal("5"), "unit_price": Decimal("37.50")}],
        )
        accept_quotation(company=tenant_a, quotation=quotation)
        order = create_sales_order(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-02", quotation=quotation,
        )
        assert order.lines.first().unit_price == Decimal("37.50")

    def test_cannot_convert_an_unaccepted_quotation(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_quotation, create_sales_order

        fixtures = sales_fixtures_factory(tenant_a)
        quotation = create_quotation(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-01",
            lines=[{"product": fixtures["product"], "quantity": Decimal("5"), "unit_price": Decimal("20.00")}],
        )
        with pytest.raises(ValidationError, match="accepted"):
            create_sales_order(company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-02", quotation=quotation)

    def test_order_starts_draft_and_requires_confirmation_to_deliver(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures)
        assert order.status == "draft"
        with pytest.raises(ValidationError, match="draft"):
            create_delivery(
                company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                date="2026-01-05", lines=[{"so_line": order.lines.first(), "quantity": Decimal("10")}],
            )


class TestDelivery:
    def test_partial_delivery_moves_order_to_partially_delivered(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, delivered_quantity

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("100"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()

        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("40")}])
        order.refresh_from_db()
        assert order.status == "partially_delivered"
        assert delivered_quantity(so_line) == Decimal("40")

    def test_second_delivery_completes_the_order(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("100"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()

        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("40")}])
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-10", lines=[{"so_line": so_line, "quantity": Decimal("60")}])
        order.refresh_from_db()
        assert order.status == "delivered"

    def test_delivery_decrements_stock_and_posts_no_journal_entry(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.accounting.models import JournalEntry
        from apps.sales.services import confirm_sales_order, create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("20"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()

        before_je = JournalEntry.objects.for_company(tenant_a).count()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("20")}])
        after_je = JournalEntry.objects.for_company(tenant_a).count()

        assert after_je == before_je  # no accounting entry — revenue/AR wait for the invoice
        assert fixtures["product"].current_stock() == Decimal("-20")  # started at 0, delivered 20 out

    def test_over_delivery_blocked_by_default(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()

        with pytest.raises(ValidationError, match="remains undelivered"):
            create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                             date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("15")}])

    def test_over_delivery_allowed_with_explicit_override(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()

        delivery = create_delivery(
            company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
            date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("15")}], allow_over_delivery=True,
        )
        assert delivery.lines.first().quantity == Decimal("15")


class TestInvoiceFromOrderNoDoubleDecrement:
    def test_invoicing_a_delivered_line_does_not_move_stock_again(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"), unit_price=Decimal("25.00"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("10")}])

        stock_after_delivery = fixtures["product"].current_stock()
        create_invoice_from_order(
            company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-10",
            lines=[{"so_line": so_line, "quantity": Decimal("10")}],
        )
        assert fixtures["product"].current_stock() == stock_after_delivery  # unchanged by invoicing

    def test_invoice_from_order_posts_the_ar_and_revenue_entry(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.accounting.services import account_balance
        from apps.accounting.models import Account
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"), unit_price=Decimal("25.00"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("10")}])
        create_invoice_from_order(
            company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-10",
            lines=[{"so_line": so_line, "quantity": Decimal("10")}],
        )

        ar = Account.objects.for_company(tenant_a).get(code="1100")
        revenue = Account.objects.for_company(tenant_a).get(code="4000")
        assert account_balance(ar) == Decimal("250.00")
        assert account_balance(revenue) == Decimal("250.00")

    def test_partial_invoicing_across_multiple_invoices(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order, invoiced_quantity

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"), unit_price=Decimal("15.00"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("10")}])

        create_invoice_from_order(company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-06",
                                   lines=[{"so_line": so_line, "quantity": Decimal("6")}])
        create_invoice_from_order(company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-07",
                                   lines=[{"so_line": so_line, "quantity": Decimal("4")}])
        assert invoiced_quantity(so_line) == Decimal("10")

    def test_cannot_invoice_more_than_delivered_by_default(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("5")}])

        with pytest.raises(ValidationError, match="delivered-but-uninvoiced"):
            create_invoice_from_order(company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-06",
                                       lines=[{"so_line": so_line, "quantity": Decimal("8")}])

    def test_over_invoicing_allowed_with_explicit_override(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"), unit_price=Decimal("10.00"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("5")}])

        invoice = create_invoice_from_order(
            company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-06",
            lines=[{"so_line": so_line, "quantity": Decimal("8")}], allow_over_invoicing=True,
        )
        assert invoice.total == Decimal("80.00")

    def test_invoice_is_traceable_back_to_the_order(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery, create_invoice_from_order

        fixtures = sales_fixtures_factory(tenant_a)
        order = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, quantity=Decimal("10"))
        confirm_sales_order(company=tenant_a, sales_order=order)
        so_line = order.lines.first()
        create_delivery(company=tenant_a, user=tenant_a_owner, sales_order=order, warehouse=fixtures["warehouse"],
                         date="2026-01-05", lines=[{"so_line": so_line, "quantity": Decimal("10")}])
        invoice = create_invoice_from_order(company=tenant_a, user=tenant_a_owner, sales_order=order, date="2026-01-06",
                                             lines=[{"so_line": so_line, "quantity": Decimal("10")}])

        assert invoice.sales_order_id == order.id
        assert invoice.lines.first().so_line_id == so_line.id


class TestDirectInvoiceFlowStillWorks:
    def test_direct_invoice_unaffected_by_phase_33(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        """The existing walk-in/POS-style path (no order/delivery at all)
        must keep working exactly as before — acceptance criteria:
        'direct invoice still works'."""
        from apps.sales.services import create_invoice
        from apps.accounting.services import account_balance
        from apps.accounting.models import Account

        fixtures = sales_fixtures_factory(tenant_a)
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"], date="2026-01-01",
            lines=[{"product": fixtures["product"], "quantity": Decimal("3"), "unit_price": Decimal("100.00")}],
            warehouse=fixtures["warehouse"],
        )
        assert invoice.total == Decimal("300.00")
        assert fixtures["product"].current_stock() == Decimal("-3")
        assert account_balance(Account.objects.for_company(tenant_a).get(code="1100")) == Decimal("300.00")


class TestTenantIsolationAndApi:
    def test_so_line_from_another_order_is_rejected(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import confirm_sales_order, create_delivery

        fixtures = sales_fixtures_factory(tenant_a)
        order1 = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures)
        order2 = _make_order(tenant_a, tenant_a_owner, fixtures["customer"], fixtures)
        confirm_sales_order(company=tenant_a, sales_order=order1)
        confirm_sales_order(company=tenant_a, sales_order=order2)

        with pytest.raises(ValidationError, match="does not belong to this sales order"):
            create_delivery(
                company=tenant_a, user=tenant_a_owner, sales_order=order1, warehouse=fixtures["warehouse"],
                date="2026-01-05", lines=[{"so_line": order2.lines.first(), "quantity": Decimal("1")}],
            )

    def test_owner_can_run_full_flow_via_api(self, tenant_a, as_tenant_a_owner, sales_fixtures_factory):
        fixtures = sales_fixtures_factory(tenant_a)
        resp = as_tenant_a_owner.post("/api/sales/orders/", {
            "customer": fixtures["customer"].id, "date": "2026-01-01",
            "lines": [{"product": fixtures["product"].id, "quantity": "10", "unit_price": "12.00"}],
        }, format="json")
        assert resp.status_code == 201, resp.data
        order_id = resp.data["id"]

        resp = as_tenant_a_owner.post(f"/api/sales/orders/{order_id}/confirm/")
        assert resp.status_code == 200, resp.data
        line_id = resp.data["lines"][0]["id"]

        resp = as_tenant_a_owner.post(f"/api/sales/orders/{order_id}/deliver/", {
            "warehouse": fixtures["warehouse"].id, "date": "2026-01-05",
            "lines": [{"so_line": line_id, "quantity": "10"}],
        }, format="json")
        assert resp.status_code == 201, resp.data

        resp = as_tenant_a_owner.post(f"/api/sales/orders/{order_id}/invoice/", {
            "date": "2026-01-06", "lines": [{"so_line": line_id, "quantity": "10"}],
        }, format="json")
        assert resp.status_code == 201, resp.data

    def test_staff_cannot_use_override_delivery(self, tenant_a, member_factory, sales_fixtures_factory):
        from conftest import jwt_client

        fixtures = sales_fixtures_factory(tenant_a)
        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        resp = client.post("/api/sales/orders/", {
            "customer": fixtures["customer"].id, "date": "2026-01-01",
            "lines": [{"product": fixtures["product"].id, "quantity": "10", "unit_price": "5.00"}],
        }, format="json")
        assert resp.status_code == 201, resp.data
        order_id = resp.data["id"]
        client.post(f"/api/sales/orders/{order_id}/confirm/")
        line_id = resp.data["lines"][0]["id"]

        resp = client.post(f"/api/sales/orders/{order_id}/deliver/", {
            "warehouse": fixtures["warehouse"].id, "date": "2026-01-05", "allow_over_delivery": True,
            "lines": [{"so_line": line_id, "quantity": "50"}],
        }, format="json")
        assert resp.status_code == 403
