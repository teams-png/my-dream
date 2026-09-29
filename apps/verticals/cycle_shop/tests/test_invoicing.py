"""Phase 26 — sell_unit() now invoices via sales.services.create_invoice()."""
from decimal import Decimal

import pytest

from apps.modules.models import Module, CompanyModule
from apps.verticals.cycle_shop.models import CycleUnit


@pytest.fixture
def cycle_shop_enabled(tenant_a):
    module, _ = Module.objects.get_or_create(code="cycle_shop", defaults={"name": "Cycle Shop"})
    CompanyModule.objects.get_or_create(company=tenant_a, module=module, defaults={"is_active": True})


@pytest.fixture
def unit(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="MTB-26")
    return CycleUnit.objects.create(
        company=tenant_a, product=f["product"], serial_number="CY-0001",
        purchase_price=Decimal("120.00"), status="in_stock",
    ), f["warehouse"], f["customer"]


@pytest.mark.django_db
class TestCycleShopInvoicing:
    def test_sell_creates_invoice_and_marks_sold(self, as_tenant_a_owner, cycle_shop_enabled, unit, tenant_a):
        cycle_unit, warehouse, customer = unit
        resp = as_tenant_a_owner.post(
            f"/api/cycle-shop/units/{cycle_unit.id}/sell/",
            {"buyer": customer.id, "warehouse": warehouse.id, "sold_price": "180.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 200, resp.content
        cycle_unit.refresh_from_db()
        assert cycle_unit.status == "sold"

        from apps.sales.models import SalesInvoice
        invoice = SalesInvoice.objects.for_company(tenant_a).latest("id")
        assert invoice.total == Decimal("180.00")

    def test_sell_without_buyer_uses_walkin_customer(self, as_tenant_a_owner, cycle_shop_enabled, unit, tenant_a):
        cycle_unit, warehouse, _ = unit
        resp = as_tenant_a_owner.post(
            f"/api/cycle-shop/units/{cycle_unit.id}/sell/",
            {"warehouse": warehouse.id, "sold_price": "180.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 200, resp.content
        from apps.sales.models import SalesInvoice
        assert SalesInvoice.objects.for_company(tenant_a).latest("id").customer.name == "Walk-in Customer"

    def test_cannot_sell_twice(self, as_tenant_a_owner, cycle_shop_enabled, unit):
        cycle_unit, warehouse, customer = unit
        payload = {"buyer": customer.id, "warehouse": warehouse.id, "sold_price": "180.00", "sold_date": "2026-01-20"}
        assert as_tenant_a_owner.post(f"/api/cycle-shop/units/{cycle_unit.id}/sell/", payload).status_code == 200
        assert as_tenant_a_owner.post(f"/api/cycle-shop/units/{cycle_unit.id}/sell/", payload).status_code == 400
