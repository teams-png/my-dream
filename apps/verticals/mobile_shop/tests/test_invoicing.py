"""Phase 26 — sell_unit() now invoices via sales.services.create_invoice()."""
from decimal import Decimal

import pytest

from apps.modules.models import Module, CompanyModule
from apps.verticals.mobile_shop.models import MobileUnit


@pytest.fixture
def mobile_shop_enabled(tenant_a):
    module, _ = Module.objects.get_or_create(code="mobile_shop", defaults={"name": "Mobile Shop"})
    CompanyModule.objects.get_or_create(company=tenant_a, module=module, defaults={"is_active": True})


@pytest.fixture
def unit(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="IPHONE-13")
    return MobileUnit.objects.create(
        company=tenant_a, product=f["product"], imei="123456789012345",
        purchase_price=Decimal("400.00"), status="in_stock",
    ), f["warehouse"], f["customer"]


@pytest.mark.django_db
class TestMobileShopInvoicing:
    def test_sell_creates_invoice_and_marks_sold(self, as_tenant_a_owner, mobile_shop_enabled, unit, tenant_a):
        mobile_unit, warehouse, customer = unit
        resp = as_tenant_a_owner.post(
            f"/api/mobile-shop/units/{mobile_unit.id}/sell/",
            {"buyer": customer.id, "warehouse": warehouse.id, "sold_price": "550.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 200, resp.content
        mobile_unit.refresh_from_db()
        assert mobile_unit.status == "sold"

        from apps.sales.models import SalesInvoice
        invoice = SalesInvoice.objects.for_company(tenant_a).latest("id")
        assert invoice.total == Decimal("550.00")
        assert invoice.customer_id == customer.id

    def test_sell_without_buyer_uses_walkin_customer(self, as_tenant_a_owner, mobile_shop_enabled, unit, tenant_a):
        mobile_unit, warehouse, _ = unit
        resp = as_tenant_a_owner.post(
            f"/api/mobile-shop/units/{mobile_unit.id}/sell/",
            {"warehouse": warehouse.id, "sold_price": "550.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 200, resp.content
        from apps.sales.models import SalesInvoice
        invoice = SalesInvoice.objects.for_company(tenant_a).latest("id")
        assert invoice.customer.name == "Walk-in Customer"

    def test_cannot_sell_twice(self, as_tenant_a_owner, mobile_shop_enabled, unit):
        mobile_unit, warehouse, customer = unit
        payload = {"buyer": customer.id, "warehouse": warehouse.id, "sold_price": "550.00", "sold_date": "2026-01-20"}
        first = as_tenant_a_owner.post(f"/api/mobile-shop/units/{mobile_unit.id}/sell/", payload)
        assert first.status_code == 200
        second = as_tenant_a_owner.post(f"/api/mobile-shop/units/{mobile_unit.id}/sell/", payload)
        assert second.status_code == 400

        from apps.sales.models import SalesInvoice
        assert SalesInvoice.objects.for_company(mobile_unit.company).count() == 1

    def test_warehouse_from_other_tenant_rejected(self, as_tenant_a_owner, mobile_shop_enabled, unit, tenant_b, sales_fixtures_factory):
        mobile_unit, _, customer = unit
        other_warehouse = sales_fixtures_factory(tenant_b, sku="OTHER-SKU")["warehouse"]
        resp = as_tenant_a_owner.post(
            f"/api/mobile-shop/units/{mobile_unit.id}/sell/",
            {"buyer": customer.id, "warehouse": other_warehouse.id, "sold_price": "550.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 400
        mobile_unit.refresh_from_db()
        assert mobile_unit.status == "in_stock"
