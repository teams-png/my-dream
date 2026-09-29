"""
Phase 27 (part 2) — purchase-side return processing. Mirrors
apps/sales/tests/test_invoice_flow.py's style and
apps.sales.services.process_return's shape, opposite direction: goods
leave stock and the journal reversal is Dr AP-or-Cash / Cr Inventory
instead of Dr Sales Revenue / Cr AR-or-Cash.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.purchases.services import create_purchase, process_purchase_return
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def supplier(tenant_a):
    return Supplier.objects.create(company=tenant_a, name="Acme Supplies")


@pytest.fixture
def purchase(tenant_a, tenant_a_owner, sales_fixtures_factory, supplier):
    fx = sales_fixtures_factory(tenant_a, sku="SKU-PUR")
    p = create_purchase(
        company=tenant_a, user=tenant_a_owner, supplier=supplier, date="2026-01-10",
        lines=[{"product": fx["product"], "quantity": Decimal("5"), "unit_cost": Decimal("40.00")}],
        warehouse=fx["warehouse"],
    )
    return p, fx


class TestPurchaseReturnServiceSideEffects:
    def test_return_totals_and_lines(self, tenant_a, tenant_a_owner, purchase):
        p, fx = purchase
        ret = process_purchase_return(
            company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
            warehouse=fx["warehouse"], reason="damaged goods",
            lines=[{"product": fx["product"], "quantity": Decimal("2"), "unit_cost": Decimal("40.00")}],
        )
        assert ret.total == Decimal("80.00")
        assert ret.reason == "damaged goods"
        assert ret.refund_method == "supplier_credit"
        assert ret.lines.count() == 1
        assert ret.lines.first().line_total == Decimal("80.00")

    def test_return_reduces_stock(self, tenant_a, tenant_a_owner, purchase):
        p, fx = purchase
        assert fx["product"].current_stock() == Decimal("5")

        process_purchase_return(
            company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
            warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("2"), "unit_cost": Decimal("40.00")}],
        )
        assert fx["product"].current_stock() == Decimal("3")

    def test_supplier_credit_return_posts_balanced_journal_entry_against_ap(
        self, tenant_a, tenant_a_owner, purchase
    ):
        from apps.accounting.services import account_balance
        from apps.accounting.models import Account

        p, fx = purchase
        ap_account = Account.objects.for_company(tenant_a).get(code="2000")
        inventory_account = Account.objects.for_company(tenant_a).get(code="1200")
        ap_before = account_balance(ap_account)
        inventory_before = account_balance(inventory_account)

        ret = process_purchase_return(
            company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
            warehouse=fx["warehouse"], refund_method="supplier_credit",
            lines=[{"product": fx["product"], "quantity": Decimal("2"), "unit_cost": Decimal("40.00")}],
        )

        assert ret.journal_entry is not None
        je = ret.journal_entry
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("80.00")

        # AP is a liability: debiting it reduces the balance (we owe the supplier less).
        assert account_balance(ap_account) == ap_before - Decimal("80.00")
        # Inventory is an asset: crediting it reduces the balance (goods left stock).
        assert account_balance(inventory_account) == inventory_before - Decimal("80.00")

    def test_cash_refund_return_hits_cash_not_ap(self, tenant_a, tenant_a_owner, purchase):
        from apps.accounting.services import account_balance
        from apps.accounting.models import Account

        p, fx = purchase
        cash_account = Account.objects.for_company(tenant_a).get(code="1000")
        ap_account = Account.objects.for_company(tenant_a).get(code="2000")
        cash_before = account_balance(cash_account)
        ap_before = account_balance(ap_account)

        process_purchase_return(
            company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
            warehouse=fx["warehouse"], refund_method="cash",
            lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_cost": Decimal("40.00")}],
        )

        assert account_balance(cash_account) == cash_before + Decimal("40.00")
        assert account_balance(ap_account) == ap_before  # untouched by a cash refund

    def test_return_with_no_lines_is_rejected(self, tenant_a, tenant_a_owner, purchase):
        p, fx = purchase
        with pytest.raises(ValidationError):
            process_purchase_return(
                company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
                warehouse=fx["warehouse"], lines=[],
            )

    def test_return_for_non_stock_tracked_product_skips_stock_movement(
        self, tenant_a, tenant_a_owner, purchase
    ):
        from apps.inventory.models import StockMovement

        p, fx = purchase
        fx["product"].is_stock_tracked = False
        fx["product"].save(update_fields=["is_stock_tracked"])

        before = StockMovement.objects.for_company(tenant_a).filter(product=fx["product"]).count()
        process_purchase_return(
            company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
            warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_cost": Decimal("40.00")}],
        )
        after = StockMovement.objects.for_company(tenant_a).filter(product=fx["product"]).count()
        assert after == before


class TestPurchaseReturnAtomicity:
    def test_failure_during_journal_posting_rolls_back_the_whole_return(
        self, tenant_a, tenant_a_owner, purchase, monkeypatch
    ):
        from apps.purchases import services as purchase_services
        from apps.purchases.models import PurchaseReturn
        from apps.inventory.models import StockMovement

        p, fx = purchase

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated failure while posting the journal entry")

        monkeypatch.setattr(purchase_services, "post_journal_entry", _boom)

        with pytest.raises(RuntimeError):
            purchase_services.process_purchase_return(
                company=tenant_a, user=tenant_a_owner, purchase=p, date="2026-01-15",
                warehouse=fx["warehouse"],
                lines=[{"product": fx["product"], "quantity": Decimal("1"), "unit_cost": Decimal("40.00")}],
            )

        assert PurchaseReturn.objects.for_company(tenant_a).count() == 0
        # the stock movement written before the (failed) journal step must not remain committed either
        assert StockMovement.objects.for_company(tenant_a).filter(reason="purchase_return").count() == 0


class TestPurchaseReturnAPI:
    def test_record_return_via_api(self, as_tenant_a_owner, purchase):
        p, fx = purchase
        resp = as_tenant_a_owner.post(
            f"/api/purchases/purchases/{p.id}/record_return/",
            {
                "date": "2026-01-15",
                "warehouse": fx["warehouse"].id,
                "reason": "wrong size",
                "refund_method": "supplier_credit",
                "lines": [{"product": fx["product"].id, "quantity": "2", "unit_cost": "40.00"}],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["total"] == "80.00"
        assert resp.data["refund_method"] == "supplier_credit"

    def test_record_return_rejects_cross_tenant_warehouse(
        self, as_tenant_a_owner, purchase, tenant_b, tenant_b_owner, sales_fixtures_factory
    ):
        p, fx = purchase
        other_fx = sales_fixtures_factory(tenant_b, sku="SKU-OTHER")

        resp = as_tenant_a_owner.post(
            f"/api/purchases/purchases/{p.id}/record_return/",
            {
                "date": "2026-01-15",
                "warehouse": other_fx["warehouse"].id,  # belongs to tenant_b, not tenant_a
                "lines": [{"product": fx["product"].id, "quantity": "1", "unit_cost": "40.00"}],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_record_return_rejects_cross_tenant_product(
        self, as_tenant_a_owner, purchase, tenant_b, sales_fixtures_factory
    ):
        p, fx = purchase
        other_fx = sales_fixtures_factory(tenant_b, sku="SKU-OTHER-2")

        resp = as_tenant_a_owner.post(
            f"/api/purchases/purchases/{p.id}/record_return/",
            {
                "date": "2026-01-15",
                "warehouse": fx["warehouse"].id,
                "lines": [{"product": other_fx["product"].id, "quantity": "1", "unit_cost": "40.00"}],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_tenant_b_cannot_return_against_tenant_a_purchase(self, as_tenant_b_owner, purchase):
        p, fx = purchase
        resp = as_tenant_b_owner.post(
            f"/api/purchases/purchases/{p.id}/record_return/",
            {
                "date": "2026-01-15",
                "warehouse": fx["warehouse"].id,
                "lines": [{"product": fx["product"].id, "quantity": "1", "unit_cost": "40.00"}],
            },
            format="json",
        )
        # get_object() scopes to request.company — a tenant_a purchase id is invisible to tenant_b.
        assert resp.status_code == 404
