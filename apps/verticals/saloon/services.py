"""
Phase 26 (part 2) — closes the invoice-linkage TODO left since this file
was first written, same shape as apps.verticals.spa.services (Phase 23).
A walk-in appointment and a package purchase are both money changing
hands, so both now go through sales.services.create_invoice() before the
row that represents "this has been paid for" gets created. A
package-covered appointment is different — the money was already
collected (and invoiced) when the package itself was sold, so completing
it must NOT create a second charge; it only decrements
sessions_remaining. That's why book_appointment() only invoices in the
walk-in branch, and complete_appointment() never invoices at all.

Known accepted quirk (same as spa/gym): invoicing a service through the
same sales.services.create_invoice() path used for physical products also
writes a StockMovement for the service "product," which has no physical
meaning. The linked Products created below are marked
is_stock_tracked=False specifically to avoid that, same as spa's.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.employees.services import record_commission
from apps.sales.services import create_invoice

from .models import Appointment, CustomerPackage, SaloonService, ServicePackage


@transaction.atomic
def create_saloon_service(*, company, name, duration_minutes, price, category=None, unit=None):
    """Creates the SaloonService's linked service Product in the same transaction — mirrors spa.services.create_spa_service."""
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="session")

    product = Product.objects.create(
        company=company, sku=f"SLN-SVC-{name.upper().replace(' ', '-')}", name=f"Saloon Service — {name}",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return SaloonService.objects.create(
        company=company, name=name, duration_minutes=duration_minutes, price=price, product=product,
    )


@transaction.atomic
def create_service_package(*, company, name, service, session_count, price, category=None, unit=None):
    """Same pattern, for the bundled-sessions product a CustomerPackage is purchased against."""
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="package")

    product = Product.objects.create(
        company=company, sku=f"SLN-PKG-{name.upper().replace(' ', '-')}", name=f"Saloon Package — {name}",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return ServicePackage.objects.create(
        company=company, name=name, service=service, session_count=session_count, price=price, product=product,
    )


@transaction.atomic
def book_appointment(
    *, company, user, customer, service, stylist, scheduled_at, warehouse, price=None,
    commission_rate_percent=Decimal("0"), customer_package=None,
):
    """Walk-in: invoices immediately at booking time. Package-covered: no invoice here (already paid at purchase)."""
    if isinstance(scheduled_at, str):
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
                "This SaloonService has no linked Product — create services via "
                "saloon.services.create_saloon_service() so walk-in bookings can invoice correctly."
            )
        create_invoice(
            company=company, user=user, customer=customer, date=scheduled_at.date(), warehouse=warehouse,
            lines=[{"product": service.product, "quantity": Decimal("1"), "unit_price": price or service.price}],
        )

    return Appointment.objects.create(
        company=company, customer=customer, service=service, stylist=stylist,
        customer_package=customer_package, scheduled_at=scheduled_at,
        price=price if price is not None else service.price,
        commission_rate_percent=commission_rate_percent, status="booked",
    )


@transaction.atomic
def complete_appointment(appointment):
    """Never invoices — payment already happened at booking time or package-purchase time."""
    appointment.status = "completed"
    appointment.save(update_fields=["status"])

    if appointment.customer_package is not None:
        pkg = appointment.customer_package
        pkg.sessions_remaining = max(0, pkg.sessions_remaining - 1)
        pkg.save(update_fields=["sessions_remaining"])

    if appointment.commission_rate_percent:
        commission_amount = (appointment.price * appointment.commission_rate_percent) / Decimal("100")
        record_commission(
            company=appointment.company, employee=appointment.stylist,
            reference_type="saloon.Appointment", reference_id=appointment.id,
            amount=commission_amount, date=appointment.scheduled_at.date(),
        )

    return appointment


def cancel_appointment(appointment, *, no_show=False):
    appointment.status = "no_show" if no_show else "cancelled"
    appointment.save(update_fields=["status"])
    return appointment


@transaction.atomic
def purchase_package(*, company, user, customer, package, purchased_on, warehouse):
    """Invoices the package's price against its linked service Product, then creates the CustomerPackage row."""
    if package.product_id is None:
        raise ValueError(
            "This ServicePackage has no linked Product — create packages via "
            "saloon.services.create_service_package() so purchases can invoice correctly."
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
