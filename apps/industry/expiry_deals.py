"""
Near-expiry discount and refill subscriptions (supplement shops, pharmacies, any shop selling from batches).

Near expiry: billing sells the batch that expires first (FEFO). While that batch expires within the rule's
days, the item's price drops by the rule's percent — in the POS and in sales.services.resolve_commercial_price,
so the screen and the bill always agree.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import NearExpiryRule, RefillSubscription

CENT = Decimal("0.01")


def rule_for(company):
    rule = NearExpiryRule.objects.filter(company=company).first()
    return rule or NearExpiryRule(company=company)


def _active(rule):
    return rule.pk and rule.enabled and rule.percent and rule.percent > 0


def first_batches(company, product_ids=None):
    """{product_id: (batch, days_left)} — the in-stock batch each item sells next (earliest expiry, not expired)."""
    from apps.inventory.models import StockMovement
    today = timezone.localdate()
    qs = StockMovement.objects.for_company(company).filter(batch__isnull=False, batch__expiry_date__gte=today)
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)
    rows = (qs.values("product_id", "batch_id", "batch__expiry_date", "batch__batch_number")
            .annotate(q=Sum("quantity")).filter(q__gt=0).order_by("product_id", "batch__expiry_date", "batch_id"))
    out = {}
    for r in rows:
        out.setdefault(r["product_id"], ({"id": r["batch_id"], "number": r["batch__batch_number"],
                                          "expiry_date": r["batch__expiry_date"], "stock": r["q"]},
                                         (r["batch__expiry_date"] - today).days))
    return out


def near_expiry(company, product_ids=None):
    """{product_id: (batch, days_left, percent)} for items whose next batch is inside the discount window."""
    rule = rule_for(company)
    if not _active(rule):
        return {}
    return {pid: (b, days, rule.percent) for pid, (b, days) in first_batches(company, product_ids).items()
            if days <= rule.days}


def price_for(company, product, price):
    """(price, label) — the near-expiry price when the item's next batch is close to expiry."""
    if product.tracking_type != "batch" or not product.is_stock_tracked:
        return price, ""
    hit = near_expiry(company, [product.id]).get(product.id)
    if not hit:
        return price, ""
    _batch, days, pct = hit
    return cut(product.selling_price, pct, price), label(pct, days)


def cut(base, pct, current):
    discounted = (Decimal(base) * (Decimal("100") - Decimal(pct)) / Decimal("100")).quantize(CENT)
    return min(Decimal(current), discounted)


def label(pct, days):
    from django.utils.translation import gettext as _
    return _("Near expiry −%(pct)s%% (%(days)s days left)") % {"pct": f"{pct:g}", "days": days}


# ------------------------------------------------------------------ refills

def due(company, within_days=3):
    today = timezone.localdate()
    return (RefillSubscription.objects.for_company(company).filter(is_active=True, next_date__lte=today + timedelta(days=within_days))
            .select_related("customer", "product").order_by("next_date"))


@transaction.atomic
def bill_refill(sub, user):
    """Makes the bill for this refill (FEFO batch, near-expiry and the subscriber's own discount) and moves the
    next date on."""
    from apps.industry.common import default_warehouse
    from apps.sales.services import create_invoice, resolve_commercial_price
    sub = RefillSubscription.objects.select_for_update().select_related("product", "customer").get(pk=sub.pk)
    today = timezone.localdate()
    price, _source, _promo = resolve_commercial_price(company=sub.company, customer=sub.customer, product=sub.product, date=today)
    if sub.discount_percent:
        price = cut(price, sub.discount_percent, price)
    invoice = create_invoice(company=sub.company, user=user, customer=sub.customer, date=today,
                             warehouse=default_warehouse(sub.company),
                             lines=[{"product": sub.product, "quantity": Decimal(sub.quantity), "unit_price": price}])
    sub.last_invoice = invoice
    sub.next_date = max(sub.next_date, today) + timedelta(days=sub.every_days)
    sub.save(update_fields=["last_invoice", "next_date"])
    return sub


def skip(sub):
    sub.next_date = max(sub.next_date, timezone.localdate()) + timedelta(days=sub.every_days)
    sub.save(update_fields=["next_date"])
    return sub


def whatsapp_text(sub):
    from django.utils.translation import gettext as _
    return _("Hi %(name)s, your %(item)s refill from %(shop)s is due on %(date)s. Reply YES and we will keep it ready%(delivery)s.") % {
        "name": sub.customer.name, "item": sub.product.name, "shop": sub.company.name,
        "date": sub.next_date.strftime("%d %b"), "delivery": _(" for delivery") if sub.delivery else ""}
