"""
Phase 32 — Purchase Order → Goods Receipt → Supplier Bill Workflow.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def _get_account(company, code):
    from apps.accounting.models import Account
    return Account.objects.for_company(company).get(code=code)


def _make_po(company, user, supplier, fixtures, quantity=Decimal("100"), unit_cost=Decimal("10.00"), date="2026-01-01"):
    from apps.purchases.services import create_purchase_order
    return create_purchase_order(
        company=company, user=user, supplier=supplier, date=date,
        lines=[{"product": fixtures["product"], "quantity": quantity, "unit_cost": unit_cost}],
    )


@pytest.fixture
def supplier_a(tenant_a):
    from apps.suppliers.models import Supplier
    return Supplier.objects.create(company=tenant_a, name="Acme Supplies")


class TestPurchaseOrderNoLedgerImpact:
    def test_creating_a_po_posts_no_journal_entry(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.accounting.models import JournalEntry

        fixtures = sales_fixtures_factory(tenant_a)
        before = JournalEntry.objects.for_company(tenant_a).count()
        _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures)
        after = JournalEntry.objects.for_company(tenant_a).count()
        assert after == before

    def test_po_starts_as_draft_and_requires_confirmation_to_receive(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a, sales_fixtures_factory2=None):
        from apps.purchases.services import create_goods_receipt
        from apps.inventory.models import Warehouse

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures)
        assert po.status == "draft"

        with pytest.raises(ValidationError, match="draft"):
            create_goods_receipt(
                company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                date="2026-01-05", lines=[{"po_line": po.lines.first(), "quantity": Decimal("10")}],
            )

    def test_confirm_then_cancel_lifecycle(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, cancel_purchase_order

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures)
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po.refresh_from_db()
        assert po.status == "confirmed"

        cancel_purchase_order(company=tenant_a, purchase_order=po)
        po.refresh_from_db()
        assert po.status == "cancelled"


class TestGoodsReceipt:
    def test_partial_receipt_moves_po_to_partially_received(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, received_quantity

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("100"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        create_goods_receipt(
            company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
            date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("40")}],
        )
        po.refresh_from_db()
        assert po.status == "partially_received"
        assert received_quantity(po_line) == Decimal("40")

    def test_second_receipt_completes_the_po(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("100"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("40")}])
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-10", lines=[{"po_line": po_line, "quantity": Decimal("60")}])
        po.refresh_from_db()
        assert po.status == "received"

    def test_receipt_increases_inventory_and_grni_not_ap(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.accounting.services import account_balance
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"), unit_cost=Decimal("50.00"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("10")}])

        assert account_balance(_get_account(tenant_a, "1200")) == Decimal("500.00")  # Inventory
        assert account_balance(_get_account(tenant_a, "2050")) == Decimal("500.00")  # GRNI liability (credit-normal balance)
        assert account_balance(_get_account(tenant_a, "2000")) == Decimal("0")  # AP untouched

    def test_receipt_increases_physical_stock(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("15"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("15")}])
        assert fixtures["product"].current_stock() == Decimal("15")

    def test_over_receipt_blocked_by_default(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        with pytest.raises(ValidationError, match="remains unreceived"):
            create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                                  date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("15")}])

    def test_over_receipt_allowed_with_explicit_override(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()

        grn = create_goods_receipt(
            company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
            date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("15")}], allow_over_receipt=True,
        )
        assert grn.lines.first().quantity == Decimal("15")


class TestBillFromGrn:
    def test_bill_reverses_grni_and_raises_ap(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.accounting.services import account_balance
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"), unit_cost=Decimal("50.00"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("10")}])

        create_bill_from_grn(
            company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-10",
            bill_number="INV-100", lines=[{"po_line": po_line, "quantity": Decimal("10")}],
        )

        assert account_balance(_get_account(tenant_a, "2050")) == Decimal("0")   # GRNI fully cleared
        assert account_balance(_get_account(tenant_a, "2000")) == Decimal("500.00")  # AP now the real liability
        assert account_balance(_get_account(tenant_a, "1200")) == Decimal("500.00")  # Inventory untouched by billing

    def test_bill_does_not_move_stock_again(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("10")}])
        create_bill_from_grn(company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-10",
                              lines=[{"po_line": po_line, "quantity": Decimal("10")}])

        assert fixtures["product"].current_stock() == Decimal("10")  # unchanged since the receipt

    def test_partial_billing_supported_across_multiple_bills(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn, billed_quantity

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"), unit_cost=Decimal("20.00"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("10")}])

        create_bill_from_grn(company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-06",
                              lines=[{"po_line": po_line, "quantity": Decimal("6")}])
        create_bill_from_grn(company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-07",
                              lines=[{"po_line": po_line, "quantity": Decimal("4")}])

        assert billed_quantity(po_line) == Decimal("10")

    def test_over_billing_blocked_by_default(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("5")}])

        with pytest.raises(ValidationError, match="received-but-unbilled"):
            create_bill_from_grn(company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-06",
                                  lines=[{"po_line": po_line, "quantity": Decimal("8")}])

    def test_over_billing_allowed_with_explicit_override(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("5")}])

        purchase = create_bill_from_grn(
            company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-06",
            lines=[{"po_line": po_line, "quantity": Decimal("8")}], allow_over_billing=True,
        )
        assert purchase.total == Decimal("80.00")

    def test_bill_is_linked_to_the_purchase_order(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt, create_bill_from_grn

        fixtures = sales_fixtures_factory(tenant_a)
        po = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures, quantity=Decimal("10"))
        confirm_purchase_order(company=tenant_a, purchase_order=po)
        po_line = po.lines.first()
        create_goods_receipt(company=tenant_a, user=tenant_a_owner, purchase_order=po, warehouse=fixtures["warehouse"],
                              date="2026-01-05", lines=[{"po_line": po_line, "quantity": Decimal("10")}])
        purchase = create_bill_from_grn(company=tenant_a, user=tenant_a_owner, purchase_order=po, date="2026-01-06",
                                         lines=[{"po_line": po_line, "quantity": Decimal("10")}])
        assert purchase.purchase_order_id == po.id


class TestTenantIsolationAndApi:
    def test_po_line_from_another_po_is_rejected(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.purchases.services import confirm_purchase_order, create_goods_receipt

        fixtures = sales_fixtures_factory(tenant_a)
        po1 = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures)
        po2 = _make_po(tenant_a, tenant_a_owner, supplier_a, fixtures)
        confirm_purchase_order(company=tenant_a, purchase_order=po1)
        confirm_purchase_order(company=tenant_a, purchase_order=po2)

        with pytest.raises(ValidationError, match="does not belong to this purchase order"):
            create_goods_receipt(
                company=tenant_a, user=tenant_a_owner, purchase_order=po1, warehouse=fixtures["warehouse"],
                date="2026-01-05", lines=[{"po_line": po2.lines.first(), "quantity": Decimal("1")}],
            )

    def test_owner_can_create_po_and_receive_via_api(self, tenant_a, as_tenant_a_owner, sales_fixtures_factory, supplier_a):
        fixtures = sales_fixtures_factory(tenant_a)
        resp = as_tenant_a_owner.post("/api/purchases/purchase-orders/", {
            "supplier": supplier_a.id, "date": "2026-01-01",
            "lines": [{"product": fixtures["product"].id, "quantity": "10", "unit_cost": "5.00"}],
        }, format="json")
        assert resp.status_code == 201, resp.data
        po_id = resp.data["id"]

        resp = as_tenant_a_owner.post(f"/api/purchases/purchase-orders/{po_id}/confirm/")
        assert resp.status_code == 200, resp.data

        line_id = resp.data["lines"][0]["id"]
        resp = as_tenant_a_owner.post(f"/api/purchases/purchase-orders/{po_id}/receive/", {
            "warehouse": fixtures["warehouse"].id, "date": "2026-01-05",
            "lines": [{"po_line": line_id, "quantity": "10"}],
        }, format="json")
        assert resp.status_code == 201, resp.data

    def test_accountant_cannot_use_override_receiving(self, tenant_a, member_factory, sales_fixtures_factory, supplier_a):
        from conftest import jwt_client

        fixtures = sales_fixtures_factory(tenant_a)
        accountant = member_factory(tenant_a, "Accountant")
        client = jwt_client(accountant)

        resp = client.post("/api/purchases/purchase-orders/", {
            "supplier": supplier_a.id, "date": "2026-01-01",
            "lines": [{"product": fixtures["product"].id, "quantity": "10", "unit_cost": "5.00"}],
        }, format="json")
        assert resp.status_code == 201, resp.data
        po_id = resp.data["id"]
        client.post(f"/api/purchases/purchase-orders/{po_id}/confirm/")
        line_id = resp.data["lines"][0]["id"]

        resp = client.post(f"/api/purchases/purchase-orders/{po_id}/receive/", {
            "warehouse": fixtures["warehouse"].id, "date": "2026-01-05", "allow_over_receipt": True,
            "lines": [{"po_line": line_id, "quantity": "50"}],
        }, format="json")
        assert resp.status_code == 403
