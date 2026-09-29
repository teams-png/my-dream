"""
Textile invoice-linkage tests — Phase 26 (part 3). Unlike spa/saloon
(one Product per named service), a tailoring order's price is custom per
order, so create_tailoring_order() invoices against one shared per-company
"Tailoring Service" placeholder Product — see the module docstring in
services.py. Mirrors the fixture convention of the other Phase 26 test
files (tenant_a / tenant_a_owner).
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def textile_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Walk-in Customer")
    return {"warehouse": warehouse, "customer": customer}


class TestCreateTailoringOrder:
    def test_creates_an_invoice_and_links_it(self, tenant_a, tenant_a_owner, textile_fixtures):
        from apps.verticals.textile.services import create_tailoring_order
        from apps.sales.models import SalesInvoice

        assert SalesInvoice.objects.for_company(tenant_a).count() == 0

        order = create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-10", expected_delivery_date="2026-01-20",
            price=Decimal("450.00"), warehouse=textile_fixtures["warehouse"],
        )

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("450.00")
        assert order.sales_invoice_id == invoices.first().id
        assert order.status == "pending"

    def test_reuses_the_same_shared_product_across_orders(self, tenant_a, tenant_a_owner, textile_fixtures):
        """Two orders shouldn't each get their own Product — one shared
        placeholder per company, per the module docstring."""
        from apps.verticals.textile.services import create_tailoring_order
        from apps.inventory.models import Product

        create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-10", expected_delivery_date="2026-01-20",
            price=Decimal("300.00"), warehouse=textile_fixtures["warehouse"],
        )
        create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-11", expected_delivery_date="2026-01-21",
            price=Decimal("500.00"), warehouse=textile_fixtures["warehouse"],
        )

        assert Product.objects.for_company(tenant_a).filter(sku="TXT-TAILORING-SERVICE").count() == 1

    def test_different_orders_can_have_different_prices(self, tenant_a, tenant_a_owner, textile_fixtures):
        """The shared Product's own selling_price is a placeholder (0) — each
        invoice line uses the order's own custom price, not the product's."""
        from apps.verticals.textile.services import create_tailoring_order
        from apps.sales.models import SalesInvoice

        create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-10", expected_delivery_date="2026-01-20",
            price=Decimal("300.00"), warehouse=textile_fixtures["warehouse"],
        )
        create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-11", expected_delivery_date="2026-01-21",
            price=Decimal("725.50"), warehouse=textile_fixtures["warehouse"],
        )

        totals = sorted(SalesInvoice.objects.for_company(tenant_a).values_list("total", flat=True))
        assert totals == [Decimal("300.00"), Decimal("725.50")]

    def test_failed_invoice_leaves_no_order(self, tenant_a, tenant_a_owner, textile_fixtures, monkeypatch):
        """Same atomicity guarantee as every other vertical in this phase."""
        from apps.verticals.textile import services as textile_services
        from apps.verticals.textile.models import TailoringOrder

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(textile_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            textile_services.create_tailoring_order(
                company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
                order_date="2026-01-10", expected_delivery_date="2026-01-20",
                price=Decimal("300.00"), warehouse=textile_fixtures["warehouse"],
            )

        assert TailoringOrder.objects.for_company(tenant_a).count() == 0

    def test_shared_product_is_not_stock_tracked(self, tenant_a, tenant_a_owner, textile_fixtures):
        """A tailoring job has no physical stock — the placeholder Product must
        not accumulate StockMovements (see services.py's module docstring)."""
        from apps.verticals.textile.services import create_tailoring_order
        from apps.inventory.models import Product

        create_tailoring_order(
            company=tenant_a, user=tenant_a_owner, customer=textile_fixtures["customer"],
            order_date="2026-01-10", expected_delivery_date="2026-01-20",
            price=Decimal("300.00"), warehouse=textile_fixtures["warehouse"],
        )

        product = Product.objects.for_company(tenant_a).get(sku="TXT-TAILORING-SERVICE")
        assert product.is_stock_tracked is False
