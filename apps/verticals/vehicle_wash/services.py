"""
Phase 26 (part 3) — closes the invoice-linkage TODO. Unlike spa/saloon
(invoice at booking) this vertical bills on completion — "a completed
wash is a sale" was already the stated intent in this file before this
phase, so complete_wash() is where sales.services.create_invoice() gets
called, not book_wash(). A cancelled or still-in-progress wash never
invoices at all.

WashPackage gets a linked service Product (create_wash_package(),
is_stock_tracked=False) the same way spa.SpaService does — packages are a
small, finite, reusable list (unlike textile's fully custom per-order
price), so one Product per package is the right shape here, not a shared
placeholder.
"""
from decimal import Decimal

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.sales.services import create_invoice

from .models import Vehicle, WashOrder, WashPackage


@transaction.atomic
def create_wash_package(*, company, name, vehicle_type, price, duration_minutes=30, description="", category=None, unit=None):
    """Creates the WashPackage's linked service Product in the same transaction — mirrors spa.services.create_spa_service."""
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="wash")

    product = Product.objects.create(
        company=company, sku=f"WSH-PKG-{name.upper().replace(' ', '-')}-{vehicle_type.upper()}",
        name=f"Vehicle Wash — {name} ({vehicle_type})",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return WashPackage.objects.create(
        company=company, name=name, vehicle_type=vehicle_type, price=price,
        duration_minutes=duration_minutes, description=description, product=product,
    )


def book_wash(*, company, vehicle, package, staff=None, scheduled_at, price=None):
    """No invoice here — see module docstring, billing happens at complete_wash()."""
    return WashOrder.objects.create(
        company=company, vehicle=vehicle, package=package, staff=staff,
        scheduled_at=scheduled_at, price=price if price is not None else package.price, status="booked",
    )


def start_wash(order):
    if order.status != "booked":
        raise ValueError(f"Order is '{order.status}', cannot start.")
    order.status = "in_progress"
    order.save(update_fields=["status"])
    return order


PAY_METHODS = ("cash", "card", "bank")


def plate(number):
    """KL 11 AB 1234 / kl11ab1234 → the same vehicle: upper case, single spaces."""
    return " ".join((number or "").upper().split())[:30]


@transaction.atomic
def vehicle_for(*, company, number, owner_name="", phone="", vehicle_type="car", make="", model="", color=""):
    """The vehicle with this number, or a new one (with a new customer when the owner is new)."""
    from apps.customers.models import Customer
    number = plate(number)
    if not number:
        raise ValueError("Type the vehicle number.")
    wanted = number.replace(" ", "")
    for v in Vehicle.objects.for_company(company).select_related("customer"):
        if v.vehicle_number.upper().replace(" ", "") == wanted:
            return v
    owner_name = (owner_name or "").strip()[:150] or number
    phone = (phone or "").strip()[:20]
    customer = (Customer.objects.for_company(company).filter(phone=phone).first() if phone else None) or \
        Customer.objects.create(company=company, name=owner_name, phone=phone)
    kinds = {k for k, _ in Vehicle.VEHICLE_TYPE}
    return Vehicle.objects.create(company=company, customer=customer, vehicle_number=number,
                                  vehicle_type=vehicle_type if vehicle_type in kinds else "car",
                                  make=(make or "")[:50], model=(model or "")[:50], color=(color or "")[:30])


def ready_message(order):
    """WhatsApp text for the owner when the car is washed and ready."""
    v, company = order.vehicle, order.company
    what = " ".join(x for x in (v.make, v.model) if x) or v.get_vehicle_type_display()
    return (f"Hi {v.customer.name}, your {what} ({v.vehicle_number}) is washed and ready at {company.name}. "
            f"{order.package.name}: {company.default_currency} {order.price:.2f}. Thank you!")


@transaction.atomic
def complete_wash(order, *, user, warehouse, method=""):
    """
    Invoices the order's price against its package's linked service
    Product, then marks the order completed — a wash is never "completed"
    without a real invoice behind it, same guarantee every other
    vertical in this phase relies on.
    """
    if order.status not in ("booked", "in_progress"):
        raise ValueError(f"Order is '{order.status}', cannot complete.")
    if order.package.product_id is None:
        raise ValueError(
            "This WashPackage has no linked Product — create packages via "
            "vehicle_wash.services.create_wash_package() so completed washes can invoice correctly."
        )

    scheduled_at = order.scheduled_at
    if isinstance(scheduled_at, str):
        # Same reasoning as spa/saloon.services.book_appointment's scheduled_at coercion:
        # a DateTimeField holds a raw string in memory until the row is fetched from the
        # DB again, and create_invoice needs a real datetime here to call .date() on it.
        parsed = parse_datetime(scheduled_at)
        if parsed is None:
            raise ValueError(f"Invalid scheduled_at value on order: {scheduled_at!r}")
        scheduled_at = parsed

    invoice = create_invoice(
        company=order.company, user=user, customer=order.vehicle.customer, date=scheduled_at.date(),
        warehouse=warehouse,
        lines=[{"product": order.package.product, "quantity": Decimal("1"), "unit_price": order.price}],
    )

    if method in PAY_METHODS and invoice.transaction_total > 0:
        from apps.sales.services import record_customer_payment
        record_customer_payment(company=order.company, user=user, customer=order.vehicle.customer, invoice=invoice,
                                amount=invoice.transaction_total, date=scheduled_at.date(), method=method)
        order.payment_method = method
    if order.staff_id:  # the washer shows in "billing by staff" in the reports
        invoice.served_by_id = order.staff_id
        invoice.save(update_fields=["served_by"])
    order.status = "completed"
    order.sales_invoice = invoice
    order.save(update_fields=["status", "sales_invoice", "payment_method"])
    return order


def cancel_wash(order):
    if order.status == "completed":
        raise ValueError("Cannot cancel a completed order.")
    order.status = "cancelled"
    order.save(update_fields=["status"])
    return order
