"""
Saloon invoice-linkage tests — Phase 26 (part 2). Mirrors
apps/verticals/spa/tests/test_appointment_invoicing.py's structure exactly,
same fixture convention (tenant_a / tenant_a_owner).
"""
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def saloon_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer
    from apps.employees.models import Employee

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Walk-in Customer")
    stylist = Employee.objects.create(company=tenant_a, name="Stylist One", role_title="Stylist")
    return {"warehouse": warehouse, "customer": customer, "stylist": stylist}


class TestCreateSaloonService:
    def test_creates_service_with_a_linked_product(self, tenant_a):
        from apps.verticals.saloon.services import create_saloon_service

        svc = create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))

        assert svc.product is not None
        assert svc.product.company_id == tenant_a.id
        assert svc.product.selling_price == Decimal("25")


class TestCreateServicePackage:
    def test_creates_package_with_a_linked_product(self, tenant_a):
        from apps.verticals.saloon.services import create_saloon_service, create_service_package

        svc = create_saloon_service(company=tenant_a, name="Beard Trim", duration_minutes=15, price=Decimal("15"))
        pkg = create_service_package(company=tenant_a, name="5x Beard Trim", service=svc, session_count=5, price=Decimal("65"))

        assert pkg.product is not None
        assert pkg.product.selling_price == Decimal("65")


class TestBookAppointmentWalkIn:
    def test_walk_in_appointment_creates_an_invoice(self, tenant_a, tenant_a_owner, saloon_fixtures):
        from apps.verticals.saloon.services import create_saloon_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))
        assert SalesInvoice.objects.for_company(tenant_a).count() == 0

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
            stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=saloon_fixtures["warehouse"],
        )

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("25.00")
        assert appt.status == "booked"

    def test_walk_in_appointment_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, saloon_fixtures):
        from apps.verticals.saloon.services import create_saloon_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_saloon_service(company=tenant_a, name="Hair Color", duration_minutes=90, price=Decimal("60"))
        book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
            stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=saloon_fixtures["warehouse"],
        )

        invoice = SalesInvoice.objects.for_company(tenant_a).get()
        je = invoice.journal_entry
        assert je is not None
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("60.00")

    def test_walk_in_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, saloon_fixtures):
        """A SaloonService created directly via the ORM (bypassing create_saloon_service) has no
        product — book_appointment must refuse a walk-in rather than silently skip invoicing."""
        from apps.verticals.saloon.models import SaloonService
        from apps.verticals.saloon.services import book_appointment

        svc = SaloonService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
                stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=saloon_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_appointment(self, tenant_a, tenant_a_owner, saloon_fixtures, monkeypatch):
        """Same atomicity guarantee as spa/gym: if the invoice step fails, no Appointment
        should be left behind."""
        from apps.verticals.saloon import services as saloon_services
        from apps.verticals.saloon.models import Appointment

        svc = saloon_services.create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(saloon_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            saloon_services.book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
                stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=saloon_fixtures["warehouse"],
            )

        assert Appointment.objects.for_company(tenant_a).count() == 0


class TestBookAppointmentPackageCovered:
    def test_package_covered_appointment_does_not_create_a_second_invoice(self, tenant_a, tenant_a_owner, saloon_fixtures):
        """The money was already collected when the package itself was purchased —
        booking (and completing) a package-covered appointment must not charge again."""
        from apps.verticals.saloon.services import (
            create_saloon_service, create_service_package, purchase_package, book_appointment, complete_appointment,
        )
        from apps.sales.models import SalesInvoice

        svc = create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))
        pkg = create_service_package(company=tenant_a, name="5x Haircut", service=svc, session_count=5, price=Decimal("110"))
        customer_package = purchase_package(
            company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], package=pkg,
            purchased_on="2026-01-01", warehouse=saloon_fixtures["warehouse"],
        )
        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # just the package purchase

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
            stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=saloon_fixtures["warehouse"], customer_package=customer_package,
        )
        complete_appointment(appt)

        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # still just one — no double charge
        customer_package.refresh_from_db()
        assert customer_package.sessions_remaining == 4

    def test_package_with_no_sessions_remaining_is_rejected(self, tenant_a, tenant_a_owner, saloon_fixtures):
        from apps.verticals.saloon.models import CustomerPackage
        from apps.verticals.saloon.services import create_saloon_service, create_service_package, book_appointment

        svc = create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))
        pkg = create_service_package(company=tenant_a, name="1x Haircut", service=svc, session_count=1, price=Decimal("25"))
        customer_package = CustomerPackage.objects.create(
            company=tenant_a, customer=saloon_fixtures["customer"], package=pkg,
            purchased_on=date(2026, 1, 1), sessions_remaining=0,
        )

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], service=svc,
                stylist=saloon_fixtures["stylist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=saloon_fixtures["warehouse"], customer_package=customer_package,
            )


class TestPurchasePackage:
    def test_purchase_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, saloon_fixtures):
        from apps.verticals.saloon.models import SaloonService, ServicePackage
        from apps.verticals.saloon.services import purchase_package

        svc = SaloonService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))
        pkg = ServicePackage.objects.create(company=tenant_a, name="Legacy Package", service=svc, session_count=3, price=Decimal("100"))

        with pytest.raises(ValueError):
            purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=saloon_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_customer_package(self, tenant_a, tenant_a_owner, saloon_fixtures, monkeypatch):
        from apps.verticals.saloon import services as saloon_services
        from apps.verticals.saloon.models import CustomerPackage

        svc = saloon_services.create_saloon_service(company=tenant_a, name="Haircut", duration_minutes=30, price=Decimal("25"))
        pkg = saloon_services.create_service_package(company=tenant_a, name="5x Haircut", service=svc, session_count=5, price=Decimal("110"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(saloon_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            saloon_services.purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=saloon_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=saloon_fixtures["warehouse"],
            )

        assert CustomerPackage.objects.for_company(tenant_a).count() == 0
