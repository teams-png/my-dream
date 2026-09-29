"""
Phase 27 (part 3) — sales-side record_return API parity.
apps.sales.services.process_return already existed (called from the
webapp/Django-template views) but had no DRF action and no dedicated
tests — this closes that gap the same way Phase 27 part 2 closed it for
purchases. Service-level side effects (totals, stock, journal balance)
already have some coverage via apps/inventory/tests/test_non_stock_products.py;
this file focuses on the API action and its IDOR guards, mirroring
apps/purchases/tests/test_purchase_return.py's API test class.
"""
from decimal import Decimal

import pytest

from apps.sales.services import create_invoice

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice(tenant_a, tenant_a_owner, sales_fixtures_factory):
    fx = sales_fixtures_factory(tenant_a, sku="SKU-INV-RET")
    inv = create_invoice(
        company=tenant_a, user=tenant_a_owner, customer=fx["customer"], date="2026-01-05",
        warehouse=fx["warehouse"],
        lines=[{"product": fx["product"], "quantity": Decimal("5"), "unit_price": Decimal("100.00")}],
    )
    return inv, fx


class TestSalesReturnAPI:
    def test_record_return_via_api(self, as_tenant_a_owner, invoice):
        inv, fx = invoice
        resp = as_tenant_a_owner.post(
            f"/api/sales/invoices/{inv.id}/record_return/",
            {
                "date": "2026-01-10",
                "warehouse": fx["warehouse"].id,
                "reason": "customer changed mind",
                "refund_method": "cash",
                "lines": [{"product": fx["product"].id, "quantity": "2", "unit_price": "100.00"}],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["total"] == "200.00"
        assert resp.data["refund_method"] == "cash"

    def test_return_reduces_stock_via_api(self, as_tenant_a_owner, invoice):
        inv, fx = invoice
        assert fx["product"].current_stock() == Decimal("-5")  # invoice fixture sold 5 with no opening stock

        resp = as_tenant_a_owner.post(
            f"/api/sales/invoices/{inv.id}/record_return/",
            {
                "date": "2026-01-10", "warehouse": fx["warehouse"].id,
                "lines": [{"product": fx["product"].id, "quantity": "2", "unit_price": "100.00"}],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        fx["product"].refresh_from_db()
        assert fx["product"].current_stock() == Decimal("-3")  # 2 units added back

    def test_record_return_rejects_cross_tenant_warehouse(
        self, as_tenant_a_owner, invoice, tenant_b, sales_fixtures_factory
    ):
        inv, fx = invoice
        other_fx = sales_fixtures_factory(tenant_b, sku="SKU-OTHER")

        resp = as_tenant_a_owner.post(
            f"/api/sales/invoices/{inv.id}/record_return/",
            {
                "date": "2026-01-10",
                "warehouse": other_fx["warehouse"].id,  # belongs to tenant_b
                "lines": [{"product": fx["product"].id, "quantity": "1", "unit_price": "100.00"}],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_record_return_rejects_cross_tenant_product(
        self, as_tenant_a_owner, invoice, tenant_b, sales_fixtures_factory
    ):
        inv, fx = invoice
        other_fx = sales_fixtures_factory(tenant_b, sku="SKU-OTHER-2")

        resp = as_tenant_a_owner.post(
            f"/api/sales/invoices/{inv.id}/record_return/",
            {
                "date": "2026-01-10",
                "warehouse": fx["warehouse"].id,
                "lines": [{"product": other_fx["product"].id, "quantity": "1", "unit_price": "100.00"}],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_tenant_b_cannot_return_against_tenant_a_invoice(self, as_tenant_b_owner, invoice):
        inv, fx = invoice
        resp = as_tenant_b_owner.post(
            f"/api/sales/invoices/{inv.id}/record_return/",
            {
                "date": "2026-01-10", "warehouse": fx["warehouse"].id,
                "lines": [{"product": fx["product"].id, "quantity": "1", "unit_price": "100.00"}],
            },
            format="json",
        )
        # get_object() scopes to request.company — a tenant_a invoice id is invisible to tenant_b.
        assert resp.status_code == 404
