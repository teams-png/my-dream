"""
Quick sale counter: "1 chaya, 2 porotta, a juice and a cake" — tap items (or type a name), change the
rate by hand if needed, and take the money in one step. Saved as a paid takeaway order with an invoice,
so it shows in orders, shift cash, reports and receipts like any other bill.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.industry.common import default_warehouse, service_product
from apps.inventory.models import Product

from . import services
from .models import RestaurantMenuItem, RestaurantShift

MAX_LINES = 60
METHODS = {"cash", "card", "bank"}


def _decimal(value, label):
    try:
        number = Decimal(str(value)).quantize(Decimal("0.001"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"Check the {label}.")
    if number < 0:
        raise ValidationError(f"The {label} can't be negative.")
    return number


def _custom_product(company, name, price):
    name = " ".join(name.split())[:120]
    if not name:
        raise ValidationError("Type a name for the extra item.")
    return service_product(company, f"QUICK-{slugify(name)[:40] or 'item'}", name, price)


def menu(company):
    """Everything the counter can sell, quick tiles first."""
    items = (RestaurantMenuItem.objects.for_company(company).filter(product__is_active=True)
             .select_related("product", "product__category").order_by("-is_quick", "sort_order", "product__name"))
    return [{"id": m.product_id, "name": m.product.name, "price": f"{m.product.selling_price:.2f}",
             "category": m.product.category.name if m.product.category else "", "quick": m.is_quick,
             "image": m.image.url if m.image else "", "veg": m.is_vegetarian} for m in items]


@transaction.atomic
def sell(*, company, user, lines, method="cash"):
    """lines: [{"product": id, "qty": 2, "price": "1.50"}] or [{"name": "Cake", "qty": 1, "price": "5"}]."""
    if method not in METHODS:
        raise ValidationError("Choose cash, card or bank.")
    if not lines:
        raise ValidationError("Add at least one item.")
    if len(lines) > MAX_LINES:
        raise ValidationError("Too many lines for one quick sale.")
    shift = RestaurantShift.objects.for_company(company).filter(status="open").first()
    order = services.create_order(company=company, channel="takeaway", waiter=user, shift=shift)
    for row in lines:
        qty = _decimal(row.get("qty", 1), "quantity")
        price = _decimal(row.get("price", 0), "rate")
        if qty <= 0:
            continue
        if row.get("product"):
            product = Product.objects.for_company(company).filter(pk=row["product"], is_active=True).first()
            if product is None:
                raise ValidationError("An item in this sale is no longer on the menu.")
        else:
            product = _custom_product(company, str(row.get("name") or ""), price)
        services.add_order_line(company=company, order=order, product=product, quantity=qty, unit_price=price,
                                notes="" if row.get("product") else "quick item", already_sold=True)
    if not order.lines.exists():
        raise ValidationError("Add at least one item.")
    invoice = services.settle_order(company=company, user=user, order=order, warehouse=default_warehouse(company),
                                    date=timezone.localdate(), payments=method)
    return order, invoice


def today(company):
    """Quick sales today: count and total, newest bills first."""
    from apps.verticals.restaurant.models import RestaurantOrder
    orders = (RestaurantOrder.objects.for_company(company).filter(
        channel="takeaway", status="paid", invoice__date=timezone.localdate(), table__isnull=True)
        .select_related("invoice").order_by("-id"))
    recent = list(orders[:8])
    total = sum((o.invoice.total for o in orders if o.invoice), Decimal("0"))
    return {"recent": recent, "count": orders.count(), "total": total}
