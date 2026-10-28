"""
Jewellery pricing from the day's gold rate:

    price = weight (g) x rate per gram for the karat
            + making charge (per gram, fixed, or % of the gold value)
            + stone / other value

The item details (weight, karat, making charge) live in Product.attributes,
set on the product form of jewellery shops.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import GoldRate

KARATS = [k for k, _ in GoldRate.KARATS]
MAKING_MODES = [("per_gram", "Per gram"), ("fixed", "Fixed amount"), ("percent", "% of gold value")]
CENT = Decimal("0.01")


def _dec(value):
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def current_rates(company, on=None):
    """{karat: rate} using the latest rate on or before the day for each karat."""
    on = on or timezone.localdate()
    rates = {}
    for rate in GoldRate.objects.for_company(company).filter(date__lte=on).order_by("karat", "-date"):
        rates.setdefault(rate.karat, rate.rate_per_gram)
    return rates


def breakdown(attributes, rates):
    """The price parts for an item, or None if it isn't priced by gold rate."""
    attrs = attributes or {}
    weight = _dec(attrs.get("weight_grams"))
    karat = (attrs.get("purity") or "").upper().replace(" ", "")
    rate = rates.get(karat)
    if not weight or weight <= 0 or rate is None:
        return None
    gold = (weight * rate).quantize(CENT)
    making_value = _dec(attrs.get("making_charge")) or Decimal("0")
    mode = attrs.get("making_mode") or "per_gram"
    if mode == "fixed":
        making = making_value
    elif mode == "percent":
        making = gold * making_value / Decimal("100")
    else:
        making = weight * making_value
    making = making.quantize(CENT)
    stones = (_dec(attrs.get("stone_value")) or Decimal("0")).quantize(CENT)
    return {"weight": weight, "karat": karat, "rate": rate, "gold": gold, "making": making, "stones": stones,
            "total": gold + making + stones}


def price(product, rates):
    parts = breakdown(product.attributes, rates)
    return parts["total"] if parts else None


@transaction.atomic
def set_rates(company, user, values, on=None):
    """values: {karat: rate}; blank karats are skipped. Returns the saved rates."""
    on = on or timezone.localdate()
    saved = []
    for karat, value in values.items():
        rate = _dec(value)
        if karat not in KARATS or rate is None:
            continue
        if rate <= 0:
            raise ValueError(f"The {karat} rate must be more than zero.")
        obj, _ = GoldRate.objects.update_or_create(company=company, karat=karat, date=on,
                                                   defaults={"rate_per_gram": rate.quantize(CENT), "updated_by": user})
        saved.append(obj)
    return saved


def old_gold_value(company, weight, karat, deduction=0, on=None):
    """(value, rate) of old gold: weight x today's rate for the karat, less the deduction %."""
    weight, deduction = _dec(weight), _dec(deduction) or Decimal("0")
    karat = (karat or "").upper().replace(" ", "")
    if weight is None or weight <= 0:
        raise ValueError("Type the old gold's weight.")
    if deduction < 0 or deduction >= 100:
        raise ValueError("The deduction must be between 0 and 100%.")
    rate = current_rates(company, on).get(karat)
    if rate is None:
        raise ValueError(f"Set today's {karat} rate first.")
    value = (weight * rate * (Decimal("100") - deduction) / Decimal("100")).quantize(CENT)
    return value, rate


@transaction.atomic
def take_old_gold(company, user, invoice, weight, karat, deduction=0):
    """Records old gold given towards a bill and pays the bill with its value (up to what is due)."""
    from apps.sales.services import record_customer_payment
    from .models import OldGoldExchange
    value, rate = old_gold_value(company, weight, karat, deduction, on=invoice.date)
    value = min(value, invoice.total - invoice.amount_paid)
    if value <= 0:
        return None
    exchange = OldGoldExchange.objects.create(
        company=company, customer=invoice.customer, invoice=invoice, date=invoice.date, karat=karat.upper(),
        weight_grams=_dec(weight).quantize(Decimal("0.001")), rate_per_gram=rate,
        deduction_percent=_dec(deduction) or 0, value=value, created_by=user)
    record_customer_payment(company=company, user=user, customer=invoice.customer, amount=value, date=invoice.date,
                            invoice=invoice, method="old_gold")
    return exchange


@transaction.atomic
def apply_to_products(company, products=None):
    """Writes today's gold price into each item's selling price. Returns how many changed."""
    from apps.inventory.models import Product
    rates = current_rates(company)
    changed = 0
    for product in products if products is not None else Product.objects.for_company(company).filter(is_active=True):
        new_price = price(product, rates)
        if new_price is not None and new_price != product.selling_price:
            product.selling_price = new_price
            product.save(update_fields=["selling_price"])
            changed += 1
    return changed
