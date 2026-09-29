"""
Phase 24 — non-stock / service product distinction.

Closes the quirk flagged in the gym (Phase 22) and spa (Phase 23) vertical
notes: invoicing a service through sales.services.create_invoice() used to
write a StockMovement for it too, even though a membership/session has no
physical stock — making Product.current_stock() drift negative and
polluting reports.stock_report / the low-stock notification sweep.
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def _make_service_product(company, sku="SVC-1"):
    from apps.inventory.models import Product, Unit

    unit = Unit.objects.create(company=company, name="session")
    return Product.objects.create(
        company=company, sku=sku, name="Some Service", unit=unit,
        cost_price=Decimal("0"), selling_price=Decimal("50.00"), is_stock_tracked=False,
    )


class TestNonStockProductInvoicing:
    def test_create_invoice_skips_stock_movement_for_non_stock_product(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice
        from apps.inventory.models import StockMovement

        fx = sales_fixtures_factory(tenant_a)
        service_product = _make_service_product(tenant_a)

        create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"], date="2026-01-05",
            warehouse=fx["warehouse"],
            lines=[{"product": service_product, "quantity": Decimal("1"), "unit_price": Decimal("50.00")}],
        )

        assert not StockMovement.objects.filter(product=service_product).exists()
        assert service_product.current_stock() == 0

    def test_create_invoice_still_writes_stock_movement_for_tracked_product(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice
        from apps.inventory.models import StockMovement
        from apps.inventory.services import record_stock_movement

        fx = sales_fixtures_factory(tenant_a)
        record_stock_movement(
            company=tenant_a, product=fx["product"], warehouse=fx["warehouse"],
            quantity=Decimal("10"), reason="purchase",
        )

        create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"], date="2026-01-05",
            warehouse=fx["warehouse"],
            lines=[{"product": fx["product"], "quantity": Decimal("3"), "unit_price": Decimal("100.00")}],
        )

        assert StockMovement.objects.filter(product=fx["product"], reason="sale").exists()
        assert fx["product"].current_stock() == 7

    def test_process_return_skips_stock_movement_for_non_stock_product(
        self, tenant_a, tenant_a_owner, sales_fixtures_factory
    ):
        from apps.sales.services import create_invoice, process_return
        from apps.inventory.models import StockMovement

        fx = sales_fixtures_factory(tenant_a)
        service_product = _make_service_product(tenant_a, sku="SVC-2")
        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx["customer"], date="2026-01-05",
            warehouse=fx["warehouse"],
            lines=[{"product": service_product, "quantity": Decimal("1"), "unit_price": Decimal("50.00")}],
        )

        process_return(
            company=tenant_a, user=tenant_a_owner, invoice=invoice, date="2026-01-06",
            warehouse=fx["warehouse"],
            lines=[{"product": service_product, "quantity": Decimal("1"), "unit_price": Decimal("50.00")}],
        )

        assert not StockMovement.objects.filter(product=service_product).exists()

    def test_stock_report_excludes_non_stock_products(self, tenant_a, sales_fixtures_factory):
        from apps.reports.services import stock_report

        fx = sales_fixtures_factory(tenant_a)
        service_product = _make_service_product(tenant_a, sku="SVC-3")

        report = stock_report(tenant_a)
        skus_in_report = {row["sku"] for row in report["products"]}

        assert fx["product"].sku in skus_in_report
        assert service_product.sku not in skus_in_report

    def test_low_stock_check_ignores_non_stock_products(self, tenant_a):
        from apps.notifications.services import check_low_stock_and_notify
        from apps.notifications.models import Notification

        service_product = _make_service_product(tenant_a, sku="SVC-4")
        service_product.reorder_level = 0
        service_product.save(update_fields=["reorder_level"])
        # current_stock() is 0, at/below reorder_level 0 — would trigger a low-stock
        # notification if it weren't excluded by is_stock_tracked=False.

        check_low_stock_and_notify(tenant_a)

        assert not Notification.objects.filter(
            company=tenant_a, notif_type="low_stock", title__contains=service_product.name,
        ).exists()


class TestGymAndSpaProductsAreNonStock:
    def test_membership_plan_product_is_non_stock(self, tenant_a):
        from apps.verticals.gym.services import create_membership_plan

        plan = create_membership_plan(
            company=tenant_a, name="Gold", duration_days=30, price=Decimal("500.00"),
        )
        assert plan.product.is_stock_tracked is False

    def test_spa_service_and_package_products_are_non_stock(self, tenant_a):
        from apps.verticals.spa.services import create_spa_service, create_service_package

        service = create_spa_service(
            company=tenant_a, name="Facial", duration_minutes=60, price=Decimal("80.00"),
        )
        package = create_service_package(
            company=tenant_a, name="Facial 5-Pack", service=service,
            session_count=5, price=Decimal("350.00"),
        )
        assert service.product.is_stock_tracked is False
        assert package.product.is_stock_tracked is False
