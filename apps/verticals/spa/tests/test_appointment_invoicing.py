"""
Spa invoice-linkage tests — closes the walk-in-appointment and
package-purchase invoice TODOs left open since apps/verticals/spa/services.py
was first written (Phase 8) and explicitly flagged as the next candidate
in Phase 22's notes ("Spa is the obvious next one"). Mirrors
apps/verticals/gym/tests/test_enrollment.py's structure and fixture
convention (tenant_a / tenant_a_owner).
"""
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def spa_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer
    from apps.employees.models import Employee

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Walk-in Customer")
    therapist = Employee.objects.create(company=tenant_a, name="Therapist One", role_title="Therapist")
    return {"warehouse": warehouse, "customer": customer, "therapist": therapist}


class TestCreateSpaService:
    def test_creates_service_with_a_linked_product(self, tenant_a):
        from apps.verticals.spa.services import create_spa_service

        svc = create_spa_service(company=tenant_a, name="Swedish Massage", duration_minutes=60, price=Decimal("80"))

        assert svc.product is not None
        assert svc.product.company_id == tenant_a.id
        assert svc.product.selling_price == Decimal("80")


class TestCreateServicePackage:
    def test_creates_package_with_a_linked_product(self, tenant_a):
        from apps.verticals.spa.services import create_spa_service, create_service_package

        svc = create_spa_service(company=tenant_a, name="Facial", duration_minutes=45, price=Decimal("50"))
        pkg = create_service_package(company=tenant_a, name="5x Facial", service=svc, session_count=5, price=Decimal("225"))

        assert pkg.product is not None
        assert pkg.product.selling_price == Decimal("225")


class TestBookAppointmentWalkIn:
    def test_walk_in_appointment_creates_an_invoice(self, tenant_a, tenant_a_owner, spa_fixtures):
        from apps.verticals.spa.services import create_spa_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_spa_service(company=tenant_a, name="Swedish Massage", duration_minutes=60, price=Decimal("80"))
        assert SalesInvoice.objects.for_company(tenant_a).count() == 0

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
            therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=spa_fixtures["warehouse"],
        )

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("80.00")
        assert appt.status == "booked"

    def test_walk_in_appointment_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, spa_fixtures):
        from apps.verticals.spa.services import create_spa_service, book_appointment
        from apps.sales.models import SalesInvoice

        svc = create_spa_service(company=tenant_a, name="Facial", duration_minutes=45, price=Decimal("50"))
        book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
            therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=spa_fixtures["warehouse"],
        )

        invoice = SalesInvoice.objects.for_company(tenant_a).get()
        je = invoice.journal_entry
        assert je is not None
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("50.00")

    def test_walk_in_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, spa_fixtures):
        """A SpaService created directly via the ORM (bypassing create_spa_service) has no
        product — book_appointment must refuse a walk-in rather than silently skip invoicing."""
        from apps.verticals.spa.models import SpaService
        from apps.verticals.spa.services import book_appointment

        svc = SpaService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
                therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=spa_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_appointment(self, tenant_a, tenant_a_owner, spa_fixtures, monkeypatch):
        """Same atomicity guarantee as gym.enroll_member / sales.create_invoice itself:
        if the invoice step fails, no Appointment should be left behind."""
        from apps.verticals.spa import services as spa_services
        from apps.verticals.spa.models import Appointment

        svc = spa_services.create_spa_service(company=tenant_a, name="Facial", duration_minutes=45, price=Decimal("50"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(spa_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            spa_services.book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
                therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=spa_fixtures["warehouse"],
            )

        assert Appointment.objects.for_company(tenant_a).count() == 0


class TestBookAppointmentPackageCovered:
    def test_package_covered_appointment_does_not_create_a_second_invoice(self, tenant_a, tenant_a_owner, spa_fixtures):
        """The money was already collected when the package itself was purchased —
        booking (and completing) a package-covered appointment must not charge again."""
        from apps.verticals.spa.services import (
            create_spa_service, create_service_package, purchase_package, book_appointment, complete_appointment,
        )
        from apps.sales.models import SalesInvoice

        svc = create_spa_service(company=tenant_a, name="Massage", duration_minutes=60, price=Decimal("80"))
        pkg = create_service_package(company=tenant_a, name="5x Massage", service=svc, session_count=5, price=Decimal("350"))
        customer_package = purchase_package(
            company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], package=pkg,
            purchased_on="2026-01-01", warehouse=spa_fixtures["warehouse"],
        )
        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # just the package purchase

        appt = book_appointment(
            company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
            therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
            warehouse=spa_fixtures["warehouse"], customer_package=customer_package,
        )
        complete_appointment(appt)

        assert SalesInvoice.objects.for_company(tenant_a).count() == 1  # still just one — no double charge
        customer_package.refresh_from_db()
        assert customer_package.sessions_remaining == 4

    def test_package_with_no_sessions_remaining_is_rejected(self, tenant_a, tenant_a_owner, spa_fixtures):
        from apps.verticals.spa.models import CustomerPackage
        from apps.verticals.spa.services import create_spa_service, create_service_package, book_appointment

        svc = create_spa_service(company=tenant_a, name="Massage", duration_minutes=60, price=Decimal("80"))
        pkg = create_service_package(company=tenant_a, name="1x Massage", service=svc, session_count=1, price=Decimal("80"))
        customer_package = CustomerPackage.objects.create(
            company=tenant_a, customer=spa_fixtures["customer"], package=pkg,
            purchased_on=date(2026, 1, 1), sessions_remaining=0,
        )

        with pytest.raises(ValueError):
            book_appointment(
                company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], service=svc,
                therapist=spa_fixtures["therapist"], scheduled_at="2026-01-15T10:00:00Z",
                warehouse=spa_fixtures["warehouse"], customer_package=customer_package,
            )


class TestPurchasePackage:
    def test_purchase_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, spa_fixtures):
        from apps.verticals.spa.models import SpaService, ServicePackage
        from apps.verticals.spa.services import purchase_package

        svc = SpaService.objects.create(company=tenant_a, name="Legacy Service", duration_minutes=30, price=Decimal("40"))
        pkg = ServicePackage.objects.create(company=tenant_a, name="Legacy Package", service=svc, session_count=3, price=Decimal("100"))

        with pytest.raises(ValueError):
            purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=spa_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_customer_package(self, tenant_a, tenant_a_owner, spa_fixtures, monkeypatch):
        from apps.verticals.spa import services as spa_services
        from apps.verticals.spa.models import CustomerPackage

        svc = spa_services.create_spa_service(company=tenant_a, name="Massage", duration_minutes=60, price=Decimal("80"))
        pkg = spa_services.create_service_package(company=tenant_a, name="5x Massage", service=svc, session_count=5, price=Decimal("350"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(spa_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            spa_services.purchase_package(
                company=tenant_a, user=tenant_a_owner, customer=spa_fixtures["customer"], package=pkg,
                purchased_on="2026-01-01", warehouse=spa_fixtures["warehouse"],
            )

        assert CustomerPackage.objects.for_company(tenant_a).count() == 0
