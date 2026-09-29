"""
Beauty Parlour invoice-linkage tests — Phase 26 (part 2). Mirrors
apps/verticals/spa/tests/test_appointment_invoicing.py's structure exactly,
same fixture convention (tenant_a / tenant_a_owner).
"""
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def beauty_parlour_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer
    from apps.employees.models import Employee

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Walk-in Customer")
    beautician = Employee.objects.create(company=tenant_a, name="Beautician One", role_title="Beautician")
    return {"warehouse": warehouse, "customer": customer, "beautician": beautician}


class TestCreateBeautyService:
    def test_creates_service_with_a_linked_product(self, tenant_a):
        from apps.verticals.beauty_parlour.services import create_beauty_service

        svc = create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))

        assert svc.product is not None
        assert svc.product.company_id == tenant_a.id
        assert svc.product.selling_price == Decimal("25")


class TestCreateServicePackage:
    def test_creates_package_with_a_linked_product(self, tenant_a):
        from apps.verticals.beauty_parlour.services import create_beauty_service, create_service_package

        svc = create_beauty_service(company=tenant_a, name="Manicure", duration_minutes=15, price=Decimal("15"))
        pkg = create_service_package(company=tenant_a, name="5x Manicure", service=svc, session_count=5, price=Decimal("65"))

        assert pkg.product is not None
        assert pkg.product.selling_price == Decimal("65")


class TestBookAppointmentWalkIn:
    def test_walk_in_appointment_creates_an_invoice(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        from apps.verticals.beauty_parlour.services import create_beauty_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))
        assert SalesInvoice.objects.for_company(tenant_a).count() == 0

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
            beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=beauty_parlour_fixtures["warehouse"],
        )

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("25.00")
        assert appt.status == "booked"

    def test_walk_in_appointment_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        from apps.verticals.beauty_parlour.services import create_beauty_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_beauty_service(company=tenant_a, name="Bridal Makeup", duration_minutes=90, price=Decimal("60"))
        book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
            beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=beauty_parlour_fixtures["warehouse"],
        )

        invoice = SalesInvoice.objects.for_company(tenant_a).get()
        je = invoice.journal_entry
        assert je is not None
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("60.00")

    def test_walk_in_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        """A BeautyService created directly via the ORM (bypassing create_beauty_service) has no
        product — book_appointment must refuse a walk-in rather than silently skip invoicing."""
        from apps.verticals.beauty_parlour.models import BeautyService
        from apps.verticals.beauty_parlour.services import book_appointment

        svc = BeautyService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
                beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=beauty_parlour_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_appointment(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures, monkeypatch):
        """Same atomicity guarantee as spa/gym: if the invoice step fails, no Appointment
        should be left behind."""
        from apps.verticals.beauty_parlour import services as beauty_parlour_services
        from apps.verticals.beauty_parlour.models import Appointment

        svc = beauty_parlour_services.create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(beauty_parlour_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            beauty_parlour_services.book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
                beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=beauty_parlour_fixtures["warehouse"],
            )

        assert Appointment.objects.for_company(tenant_a).count() == 0


class TestBookAppointmentPackageCovered:
    def test_package_covered_appointment_does_not_create_a_second_invoice(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        """The money was already collected when the package itself was purchased —
        booking (and completing) a package-covered appointment must not charge again."""
        from apps.verticals.beauty_parlour.services import (
            create_beauty_service, create_service_package, purchase_package, book_appointment, complete_appointment,
        )
        from apps.sales.models import SalesInvoice

        svc = create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))
        pkg = create_service_package(company=tenant_a, name="5x Facial", service=svc, session_count=5, price=Decimal("110"))
        customer_package = purchase_package(
            company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], package=pkg,
            purchased_on="2026-01-01", warehouse=beauty_parlour_fixtures["warehouse"],
        )
        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # just the package purchase

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
            beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=beauty_parlour_fixtures["warehouse"], customer_package=customer_package,
        )
        complete_appointment(appt)

        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # still just one — no double charge
        customer_package.refresh_from_db()
        assert customer_package.sessions_remaining == 4

    def test_package_with_no_sessions_remaining_is_rejected(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        from apps.verticals.beauty_parlour.models import CustomerPackage
        from apps.verticals.beauty_parlour.services import create_beauty_service, create_service_package, book_appointment

        svc = create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))
        pkg = create_service_package(company=tenant_a, name="1x Facial", service=svc, session_count=1, price=Decimal("25"))
        customer_package = CustomerPackage.objects.create(
            company=tenant_a, customer=beauty_parlour_fixtures["customer"], package=pkg,
            purchased_on=date(2026, 1, 1), sessions_remaining=0,
        )

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], service=svc,
                beautician=beauty_parlour_fixtures["beautician"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=beauty_parlour_fixtures["warehouse"], customer_package=customer_package,
            )


class TestPurchasePackage:
    def test_purchase_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures):
        from apps.verticals.beauty_parlour.models import BeautyService, ServicePackage
        from apps.verticals.beauty_parlour.services import purchase_package

        svc = BeautyService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))
        pkg = ServicePackage.objects.create(company=tenant_a, name="Legacy Package", service=svc, session_count=3, price=Decimal("100"))

        with pytest.raises(ValueError):
            purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=beauty_parlour_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_customer_package(self, tenant_a, tenant_a_owner, beauty_parlour_fixtures, monkeypatch):
        from apps.verticals.beauty_parlour import services as beauty_parlour_services
        from apps.verticals.beauty_parlour.models import CustomerPackage

        svc = beauty_parlour_services.create_beauty_service(company=tenant_a, name="Facial", duration_minutes=30, price=Decimal("25"))
        pkg = beauty_parlour_services.create_service_package(company=tenant_a, name="5x Facial", service=svc, session_count=5, price=Decimal("110"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(beauty_parlour_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            beauty_parlour_services.purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=beauty_parlour_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=beauty_parlour_fixtures["warehouse"],
            )

        assert CustomerPackage.objects.for_company(tenant_a).count() == 0
