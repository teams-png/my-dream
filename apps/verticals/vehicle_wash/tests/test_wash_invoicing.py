"""
Vehicle wash invoice-linkage tests — Phase 26 (part 3). Unlike spa/saloon
(invoice at booking), this vertical bills on completion — see the module
docstring in services.py. Mirrors the fixture convention of the other
Phase 26 test files (tenant_a / tenant_a_owner).
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def wash_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer
    from apps.verticals.vehicle_wash.models import Vehicle

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Ahmed Ali")
    vehicle = Vehicle.objects.create(company=tenant_a, customer=customer, vehicle_number="QA-12345", vehicle_type="car")
    return {"warehouse": warehouse, "customer": customer, "vehicle": vehicle}


class TestCreateWashPackage:
    def test_creates_package_with_a_linked_product(self, tenant_a):
        from apps.verticals.vehicle_wash.services import create_wash_package

        pkg = create_wash_package(company=tenant_a, name="Full Detail", vehicle_type="car", price=Decimal("120"))

        assert pkg.product is not None
        assert pkg.product.company_id == tenant_a.id
        assert pkg.product.selling_price == Decimal("120")
        assert pkg.product.is_stock_tracked is False


class TestBookWash:
    def test_booking_does_not_invoice(self, tenant_a, wash_fixtures):
        """Booking is not a sale yet — see module docstring, billing happens at completion."""
        from apps.verticals.vehicle_wash.services import create_wash_package, book_wash
        from apps.sales.models import SalesInvoice

        pkg = create_wash_package(company=tenant_a, name="Basic", vehicle_type="car", price=Decimal("30"))
        book_wash(
            company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg,
            scheduled_at="2026-01-15T10:00:00Z",
        )

        assert SalesInvoice.objects.for_company(tenant_a).count() == 0


class TestCompleteWash:
    def test_completing_creates_an_invoice(self, tenant_a, tenant_a_owner, wash_fixtures):
        from apps.verticals.vehicle_wash.services import create_wash_package, book_wash, complete_wash
        from apps.sales.models import SalesInvoice

        pkg = create_wash_package(company=tenant_a, name="Premium", vehicle_type="car", price=Decimal("60"))
        order = book_wash(
            company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg,
            scheduled_at="2026-01-15T10:00:00Z",
        )

        complete_wash(order, user=tenant_a_owner, warehouse=wash_fixtures["warehouse"])

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("60.00")
        order.refresh_from_db()
        assert order.status == "completed"
        assert order.sales_invoice_id == invoices.first().id

    def test_completing_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, wash_fixtures):
        from apps.verticals.vehicle_wash.services import create_wash_package, book_wash, complete_wash

        pkg = create_wash_package(company=tenant_a, name="Basic", vehicle_type="car", price=Decimal("30"))
        order = book_wash(company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg, scheduled_at="2026-01-15T10:00:00Z")
        complete_wash(order, user=tenant_a_owner, warehouse=wash_fixtures["warehouse"])

        je = order.sales_invoice.journal_entry
        assert je is not None
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("30.00")

    def test_cannot_complete_a_cancelled_wash(self, tenant_a, tenant_a_owner, wash_fixtures):
        from apps.verticals.vehicle_wash.services import create_wash_package, book_wash, cancel_wash, complete_wash

        pkg = create_wash_package(company=tenant_a, name="Basic", vehicle_type="car", price=Decimal("30"))
        order = book_wash(company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg, scheduled_at="2026-01-15T10:00:00Z")
        cancel_wash(order)

        with pytest.raises(ValueError):
            complete_wash(order, user=tenant_a_owner, warehouse=wash_fixtures["warehouse"])

    def test_completing_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, wash_fixtures):
        """A WashPackage created directly via the ORM (bypassing create_wash_package) has no
        product — complete_wash must refuse rather than silently skip invoicing."""
        from apps.verticals.vehicle_wash.models import WashPackage
        from apps.verticals.vehicle_wash.services import book_wash, complete_wash

        pkg = WashPackage.objects.create(company=tenant_a, name="Legacy Package", vehicle_type="car", price=Decimal("40"))
        order = book_wash(company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg, scheduled_at="2026-01-15T10:00:00Z")

        with pytest.raises(ValueError):
            complete_wash(order, user=tenant_a_owner, warehouse=wash_fixtures["warehouse"])

    def test_failed_invoice_leaves_order_not_completed(self, tenant_a, tenant_a_owner, wash_fixtures, monkeypatch):
        """Same atomicity guarantee as every other vertical in this phase."""
        from apps.verticals.vehicle_wash import services as wash_services

        pkg = wash_services.create_wash_package(company=tenant_a, name="Basic", vehicle_type="car", price=Decimal("30"))
        order = wash_services.book_wash(company=tenant_a, vehicle=wash_fixtures["vehicle"], package=pkg, scheduled_at="2026-01-15T10:00:00Z")

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(wash_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            wash_services.complete_wash(order, user=tenant_a_owner, warehouse=wash_fixtures["warehouse"])

        order.refresh_from_db()
        assert order.status == "booked"
        assert order.sales_invoice_id is None
