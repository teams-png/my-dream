"""
Phase 23 — closes the invoice-linkage TODO flagged since this file was
first written (Phase 7/8) and left explicitly open by Phase 22's notes
("Spa is the obvious next one"). Same shape as
apps.verticals.gym.services (Phase 22): a walk-in appointment and a
package purchase are both money changing hands, so both now go through
sales.services.create_invoice() before the row that represents "this has
been paid for" gets created. A package-covered appointment is different —
the money was already collected (and invoiced) when the package itself
was sold, so completing it must NOT create a second charge; it only
decrements sessions_remaining. That's why book_appointment() only
invoices in the walk-in branch, and complete_appointment() never invoices
at all.

Known accepted quirk (same as gym, Phase 22 notes): invoicing a service
through the same sales.services.create_invoice() path used for physical
products also writes a StockMovement for the service "product," which has
no physical meaning and makes its current_stock() drift negative over
time. Left as-is here too — a "non-stock product" distinction in
apps.inventory is a bigger, cross-cutting change (Phase 22 flagged
apps.reports.stock_report as also affected) and deserves its own reviewed
phase now that a second vertical (this one) needs it, not a scope-creep
fix bundled into this one.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.employees.services import record_commission
from apps.sales.services import create_invoice

from .models import Appointment, CustomerPackage, ServicePackage, SpaService


@transaction.atomic
def create_spa_service(*, company, name, duration_minutes, price, category=None, unit=None):
    """
    Creates the SpaService's linked service Product in the same
    transaction, so a service is never left without one — mirrors
    gym.services.create_membership_plan exactly.
    """
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="session")

    product = Product.objects.create(
        company=company, sku=f"SPA-SVC-{name.upper().replace(' ', '-')}", name=f"Spa Service — {name}",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return SpaService.objects.create(
        company=company, name=name, duration_minutes=duration_minutes, price=price, product=product,
    )


@transaction.atomic
def create_service_package(*, company, name, service, session_count, price, category=None, unit=None):
    """Same pattern, for the bundled-sessions product a CustomerPackage is purchased against."""
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="package")

    product = Product.objects.create(
        company=company, sku=f"SPA-PKG-{name.upper().replace(' ', '-')}", name=f"Spa Package — {name}",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return ServicePackage.objects.create(
        company=company, name=name, service=service, session_count=session_count, price=price, product=product,
    )


@transaction.atomic
def book_appointment(
    *, company, user, customer, service, therapist, scheduled_at, warehouse, price=None,
    commission_rate_percent=Decimal("0"), customer_package=None,
):
    """
    Walk-in (no customer_package): invoices immediately at booking time,
    same moment gym invoices at enrollment — the Appointment row is never
    created without a real invoice behind it. Package-covered: no invoice
    here at all (already paid when the package was purchased) — only the
    sessions_remaining check, unchanged from before this phase.
    """
    if isinstance(scheduled_at, str):
        # Same reasoning as gym.services.enroll_member's join_date coercion: create_invoice
        # hands its `date` straight to Django's ORM, which parses strings itself, but we need
        # a real datetime *here* first to call .date() on it for the invoice's date param.
        parsed = parse_datetime(scheduled_at)
        if parsed is None:
            raise ValueError(f"Invalid scheduled_at value: {scheduled_at!r}")
        scheduled_at = parsed

    if customer_package is not None:
        if customer_package.sessions_remaining < 1:
            raise ValueError("This package has no sessions remaining.")
    else:
        if service.product_id is None:
            raise ValueError(
                "This SpaService has no linked Product — create services via "
                "spa.services.create_spa_service() so walk-in bookings can invoice correctly."
            )
        create_invoice(
            company=company, user=user, customer=customer, date=scheduled_at.date(), warehouse=warehouse,
            lines=[{"product": service.product, "quantity": Decimal("1"), "unit_price": price or service.price}],
        )

    return Appointment.objects.create(
        company=company, customer=customer, service=service, therapist=therapist,
        customer_package=customer_package, scheduled_at=scheduled_at,
        price=price if price is not None else service.price,
        commission_rate_percent=commission_rate_percent, status="booked",
    )


@transaction.atomic
def complete_appointment(appointment):
    """
    Marks the appointment done, consumes a package session if applicable,
    and records the therapist's commission. Never invoices — see the
    module docstring for why (payment already happened at booking time or
    package-purchase time).
    """
    appointment.status = "completed"
    appointment.save(update_fields=["status"])

    if appointment.customer_package is not None:
        pkg = appointment.customer_package
        pkg.sessions_remaining = max(0, pkg.sessions_remaining - 1)
        pkg.save(update_fields=["sessions_remaining"])

    if appointment.commission_rate_percent:
        commission_amount = (appointment.price * appointment.commission_rate_percent) / Decimal("100")
        record_commission(
            company=appointment.company, employee=appointment.therapist,
            reference_type="spa.Appointment", reference_id=appointment.id,
            amount=commission_amount, date=appointment.scheduled_at.date(),
        )

    return appointment


def cancel_appointment(appointment, *, no_show=False):
    appointment.status = "no_show" if no_show else "cancelled"
    appointment.save(update_fields=["status"])
    return appointment


@transaction.atomic
def purchase_package(*, company, user, customer, package, purchased_on, warehouse):
    """
    Invoices the package's price against its linked service Product,
    then creates the CustomerPackage row only after the invoice succeeds
    — same atomicity guarantee gym.services.enroll_member relies on.
    """
    if package.product_id is None:
        raise ValueError(
            "This ServicePackage has no linked Product — create packages via "
            "spa.services.create_service_package() so purchases can invoice correctly."
        )
    if isinstance(purchased_on, str):
        purchased_on = date.fromisoformat(purchased_on)

    create_invoice(
        company=company, user=user, customer=customer, date=purchased_on, warehouse=warehouse,
        lines=[{"product": package.product, "quantity": Decimal("1"), "unit_price": package.price}],
    )

    return CustomerPackage.objects.create(
        company=company, customer=customer, package=package,
        purchased_on=purchased_on, sessions_remaining=package.session_count,
    )
