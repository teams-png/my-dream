"""
Phase 26 (part 3) — closes the invoice-linkage TODO left since this file
was first written. Unlike spa/saloon/beauty_parlour (one Product per named
service) or mobile_shop/cycle_shop (a Product that already exists per
physical unit), a tailoring order's price is custom per order — there's no
finite list of "services" to pre-create a Product for. So this uses one
shared, per-company "Tailoring Service" Product (get_or_create'd on first
use, is_stock_tracked=False, same reasoning as spa's), and passes the
order's own `price` as the invoice line's unit_price — create_invoice()
doesn't require unit_price to match the product's own selling_price, so a
single shared placeholder Product can represent any custom-priced job.

Known accepted quirk (same class as other verticals in this phase):
a StockMovement would be written if this Product weren't
is_stock_tracked=False, which it is — no drift to worry about here.
"""
from decimal import Decimal

from django.db import transaction

from apps.sales.services import create_invoice

from .models import TailoringOrder


def _get_or_create_tailoring_service_product(company):
    """One shared placeholder Product per company — see module docstring."""
    from apps.inventory.models import Product, Unit

    unit, _ = Unit.objects.get_or_create(company=company, name="job")
    product, _ = Product.objects.get_or_create(
        company=company, sku="TXT-TAILORING-SERVICE",
        defaults={
            "name": "Tailoring Service", "unit": unit,
            "cost_price": 0, "selling_price": 0, "reorder_level": 0,
            "is_active": True, "is_stock_tracked": False,
        },
    )
    return product


@transaction.atomic
def create_tailoring_order(
    *, company, user, customer, order_date, expected_delivery_date, price, warehouse,
    measurement=None, fabric_product=None, notes="",
):
    """
    Invoices the order's price against the shared Tailoring Service
    Product before the order row is created — an order is never left
    without a real invoice behind it, same guarantee every other
    vertical in this phase relies on.
    """
    service_product = _get_or_create_tailoring_service_product(company)

    invoice = create_invoice(
        company=company, user=user, customer=customer, date=order_date, warehouse=warehouse,
        lines=[{"product": service_product, "quantity": Decimal("1"), "unit_price": price}],
    )

    return TailoringOrder.objects.create(
        company=company, customer=customer, measurement=measurement,
        fabric_product=fabric_product, order_date=order_date,
        expected_delivery_date=expected_delivery_date, price=price,
        notes=notes, status="pending", sales_invoice=invoice,
    )


def mark_ready(order):
    order.status = "ready"
    order.save(update_fields=["status"])
    return order


@transaction.atomic
def mark_delivered(order, delivered_date):
    order.status = "delivered"
    order.delivered_date = delivered_date
    order.save(update_fields=["status", "delivered_date"])
    return order
