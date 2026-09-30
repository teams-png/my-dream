"""Helpers shared by the industry modules: service products and invoicing."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.inventory.models import Product, Unit, Warehouse
from apps.sales import services as sales_services

PAYMENT_METHODS = [("cash", "Cash"), ("card", "Card"), ("bank", "Bank transfer")]
MONEY = Decimal("0.01")


def money(value, field="amount"):
    try:
        amount = Decimal(str(value if value not in (None, "") else "0")).quantize(MONEY)
    except Exception:
        raise ValidationError(f"Invalid {field}.")
    if amount < 0:
        raise ValidationError(f"{field.capitalize()} cannot be negative.")
    return amount


def service_product(company, sku, name, price=Decimal("0")):
    """A non-stock product to put on invoices (room rent, course fee, rent...)."""
    unit, _ = Unit.objects.get_or_create(company=company, name="service")
    product, created = Product.objects.get_or_create(
        company=company, sku=sku,
        defaults={"name": name[:255], "unit": unit, "selling_price": price, "is_stock_tracked": False,
                  "tracking_type": "none"},
    )
    if not created and product.name != name[:255]:
        product.name = name[:255]
        product.save(update_fields=["name"])
    return product


def default_warehouse(company):
    wh = (Warehouse.objects.for_company(company).filter(is_default=True).first()
          or Warehouse.objects.for_company(company).first())
    return wh or Warehouse.objects.create(company=company, name="Main", is_default=True)


def invoice(company, user, customer, lines, date=None, discount=Decimal("0"), discount_reason=""):
    """lines: [(product, quantity, unit_price)]; zero-quantity lines are skipped."""
    rows = [{"product": p, "quantity": Decimal(q), "unit_price": Decimal(price)} for p, q, price in lines if Decimal(q) > 0]
    return sales_services.create_invoice(
        company=company, user=user, customer=customer, date=date or timezone.localdate(), lines=rows,
        warehouse=default_warehouse(company), discount_amount=discount,
        discount_reason=discount_reason if discount else "",
    )


def pay(company, user, invoice_obj, amount, method="cash", date=None):
    amount = money(amount)
    if amount <= 0:
        return None
    return sales_services.record_customer_payment(
        company=company, user=user, customer=invoice_obj.customer, amount=amount,
        date=date or timezone.localdate(), invoice=invoice_obj,
        method=method if method in dict(PAYMENT_METHODS) else "cash",
    )
