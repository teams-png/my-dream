"""Phase 26 — dispense() now invoices via sales.services.create_invoice()."""
from datetime import date
from decimal import Decimal

import pytest

from apps.modules.models import Module, CompanyModule
from apps.verticals.medical_shop.models import MedicineBatch


@pytest.fixture
def medical_shop_enabled(tenant_a):
    module, _ = Module.objects.get_or_create(code="medical_shop", defaults={"name": "Medical Shop"})
    CompanyModule.objects.get_or_create(company=tenant_a, module=module, defaults={"is_active": True})


@pytest.fixture
def batch(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="PARA-500")
    b = MedicineBatch.objects.create(
        company=tenant_a, product=f["product"], batch_number="B-001",
        expiry_date=date(2027, 1, 1), received_date=date(2026, 1, 1),
        purchase_price=Decimal("2.00"), selling_price=Decimal("5.00"),
        quantity_received=Decimal("100"), quantity_remaining=Decimal("100"),
    )
    return b, f["warehouse"], f["customer"]


@pytest.mark.django_db
class TestMedicalShopInvoicing:
    def test_dispense_creates_invoice_and_decrements_batch(self, as_tenant_a_owner, medical_shop_enabled, batch, tenant_a):
        medicine_batch, warehouse, customer = batch
        resp = as_tenant_a_owner.post(
            f"/api/medical-shop/batches/{medicine_batch.id}/dispense/",
            {"customer": customer.id, "warehouse": warehouse.id, "quantity": "10",
             "sold_price": "5.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 201, resp.content
        medicine_batch.refresh_from_db()
        assert medicine_batch.quantity_remaining == Decimal("90")

        from apps.sales.models import SalesInvoice
        invoice = SalesInvoice.objects.for_company(tenant_a).latest("id")
        assert invoice.total == Decimal("50.00")  # quantity(10) * sold_price(5.00) per unit

    def test_dispense_without_customer_uses_walkin(self, as_tenant_a_owner, medical_shop_enabled, batch, tenant_a):
        medicine_batch, warehouse, _ = batch
        resp = as_tenant_a_owner.post(
            f"/api/medical-shop/batches/{medicine_batch.id}/dispense/",
            {"warehouse": warehouse.id, "quantity": "5", "sold_price": "5.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 201, resp.content
        from apps.sales.models import SalesInvoice
        assert SalesInvoice.objects.for_company(tenant_a).latest("id").customer.name == "Walk-in Customer"

    def test_cannot_dispense_more_than_remaining(self, as_tenant_a_owner, medical_shop_enabled, batch):
        medicine_batch, warehouse, customer = batch
        resp = as_tenant_a_owner.post(
            f"/api/medical-shop/batches/{medicine_batch.id}/dispense/",
            {"customer": customer.id, "warehouse": warehouse.id, "quantity": "500",
             "sold_price": "5.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 400
        from apps.sales.models import SalesInvoice
        assert not SalesInvoice.objects.for_company(medicine_batch.company).exists()
