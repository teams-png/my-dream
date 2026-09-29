"""Phase 26 — sell() now invoices via sales.services.create_invoice()."""
from datetime import date
from decimal import Decimal

import pytest

from apps.modules.models import Module, CompanyModule
from apps.verticals.protein_shop.models import ProteinBatch


@pytest.fixture
def protein_shop_enabled(tenant_a):
    module, _ = Module.objects.get_or_create(code="protein_shop", defaults={"name": "Protein Shop"})
    CompanyModule.objects.get_or_create(company=tenant_a, module=module, defaults={"is_active": True})


@pytest.fixture
def batch(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="WHEY-1KG")
    b = ProteinBatch.objects.create(
        company=tenant_a, product=f["product"], batch_number="PB-001",
        weight_grams=1000, expiry_date=date(2027, 1, 1), received_date=date(2026, 1, 1),
        purchase_price=Decimal("20.00"), selling_price=Decimal("35.00"),
        quantity_received=Decimal("50"), quantity_remaining=Decimal("50"),
    )
    return b, f["warehouse"], f["customer"]


@pytest.mark.django_db
class TestProteinShopInvoicing:
    def test_sell_creates_invoice_and_decrements_batch(self, as_tenant_a_owner, protein_shop_enabled, batch, tenant_a):
        protein_batch, warehouse, customer = batch
        resp = as_tenant_a_owner.post(
            f"/api/protein-shop/batches/{protein_batch.id}/sell/",
            {"customer": customer.id, "warehouse": warehouse.id, "quantity": "2",
             "sold_price": "35.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 201, resp.content
        protein_batch.refresh_from_db()
        assert protein_batch.quantity_remaining == Decimal("48")

        from apps.sales.models import SalesInvoice
        invoice = SalesInvoice.objects.for_company(tenant_a).latest("id")
        assert invoice.total == Decimal("70.00")  # quantity(2) * sold_price(35.00)

    def test_sell_without_customer_uses_walkin(self, as_tenant_a_owner, protein_shop_enabled, batch, tenant_a):
        protein_batch, warehouse, _ = batch
        resp = as_tenant_a_owner.post(
            f"/api/protein-shop/batches/{protein_batch.id}/sell/",
            {"warehouse": warehouse.id, "quantity": "1", "sold_price": "35.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 201, resp.content
        from apps.sales.models import SalesInvoice
        assert SalesInvoice.objects.for_company(tenant_a).latest("id").customer.name == "Walk-in Customer"

    def test_cannot_sell_expired_batch(self, as_tenant_a_owner, protein_shop_enabled, batch, tenant_a):
        protein_batch, warehouse, customer = batch
        protein_batch.expiry_date = date(2020, 1, 1)
        protein_batch.save(update_fields=["expiry_date"])
        resp = as_tenant_a_owner.post(
            f"/api/protein-shop/batches/{protein_batch.id}/sell/",
            {"customer": customer.id, "warehouse": warehouse.id, "quantity": "1",
             "sold_price": "35.00", "sold_date": "2026-01-20"},
        )
        assert resp.status_code == 400
        from apps.sales.models import SalesInvoice
        assert not SalesInvoice.objects.for_company(tenant_a).exists()
