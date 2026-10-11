"""Home delivery with the restaurant's own riders.

    waiting ──assign──▶ assigned ──out──▶ out ──delivered (cash / card / paid already)──▶ delivered
                                              └──not delivered (reason)──▶ failed ──assign again──▶ …

A delivered order that was not paid before it left is billed when the rider hands the money over
(``handover``): cash orders as cash, card-machine orders as card. Until then the cash is "with the rider".
"""
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import DeliveryHandover, RestaurantOrder

OPEN = ("waiting", "assigned", "out", "failed")
FEE_SKU = "DELIVERY-FEE"


def board_orders(company):
    """Deliveries still to do, plus today's delivered ones."""
    today = timezone.localdate()
    return (RestaurantOrder.objects.for_company(company).filter(channel="delivery")
            .exclude(status="cancelled")
            .filter(Q(delivery_status__in=OPEN) | Q(delivery_status="delivered", delivered_at__date=today))
            .select_related("rider", "zone", "customer").prefetch_related("lines__product")
            .order_by("created_at"))


def _editable(order):
    if order.channel != "delivery" or order.status == "cancelled":
        raise ValidationError(_("This is not an open delivery order."))


def to_collect(order):
    """What the rider takes from the customer at the door (0 when the bill was paid before it left)."""
    return Decimal("0") if order.status == "paid" else order.total


def set_zone(order, zone):
    """Choose the area; its delivery charge goes on the bill as one line (replacing an earlier one)."""
    from . import services
    _editable(order)
    if order.status == "paid":
        raise ValidationError(_("The bill is already paid."))
    company = order.company
    fee_product = services._charge_product(company, FEE_SKU, "Delivery charge")
    order.lines.filter(product=fee_product).delete()
    order.zone = zone
    order.save(update_fields=["zone"])
    if zone is None:
        return Decimal("0")
    subtotal = sum((l.total for l in order.lines.all()), Decimal("0"))
    fee = zone.fee_for(subtotal)
    if fee:
        line = services.add_order_line(company=company, order=order, product=fee_product, quantity=1,
                                       unit_price=fee, notes=zone.name)
        line.sent_at = timezone.now()  # never printed on the kitchen ticket
        line.save(update_fields=["sent_at"])
    return fee


def assign(order, rider):
    _editable(order)
    if order.delivery_status == "delivered":
        raise ValidationError(_("This order is already delivered."))
    if rider is not None and (rider.company_id != order.company_id or not rider.is_active):
        raise ValidationError(_("Choose an active rider."))
    order.rider = rider
    order.delivery_status = "assigned" if rider else "waiting"
    order.save(update_fields=["rider", "delivery_status"])
    return order


def dispatch(order):
    """The rider has the food and left."""
    _editable(order)
    if order.rider is None:
        raise ValidationError(_("Choose a rider first."))
    if order.delivery_status not in ("assigned", "failed", "out"):
        raise ValidationError(_("This order is not waiting to go out."))
    order.delivery_status = "out"
    order.dispatched_at = timezone.now()
    order.save(update_fields=["delivery_status", "dispatched_at"])
    return order


def deliver(order, method):
    """Handed over at the door. ``method``: cash / card (rider's card machine) / prepaid."""
    _editable(order)
    if order.delivery_status not in ("assigned", "out"):
        raise ValidationError(_("This order is not on the way."))
    if order.status == "paid":
        method = "prepaid"
    elif method not in ("cash", "card"):
        raise ValidationError(_("How did the customer pay?"))
    now = timezone.now()
    order.delivery_status = "delivered"
    order.delivered_at = now
    order.dispatched_at = order.dispatched_at or now
    order.collect_method = method
    order.save(update_fields=["delivery_status", "delivered_at", "dispatched_at", "collect_method"])
    return order


def fail(order, reason):
    _editable(order)
    if order.delivery_status not in ("assigned", "out"):
        raise ValidationError(_("This order is not on the way."))
    order.delivery_status = "failed"
    order.delivery_note = (reason or "").strip()[:255] or _("Not delivered")
    order.save(update_fields=["delivery_status", "delivery_note"])
    return order


def unsettled(rider):
    """Delivered orders whose money the rider has not handed over yet."""
    return (RestaurantOrder.objects.for_company(rider.company).filter(rider=rider, delivery_status="delivered",
                                                                     handover__isnull=True)
            .exclude(status="cancelled").prefetch_related("lines"))


def cash_with(rider):
    return sum((o.total for o in unsettled(rider) if o.collect_method == "cash" and o.status != "paid"), Decimal("0"))


def _default_warehouse(company):
    from apps.inventory.models import Warehouse
    qs = Warehouse.objects.for_company(company).filter(is_active=True)
    return qs.filter(is_default=True).first() or qs.first()


@transaction.atomic
def handover(rider, user, warehouse=None):
    """The rider gives the money back: every delivered, unbilled order of theirs is billed now."""
    from . import services
    company = rider.company
    orders = list(unsettled(rider).select_for_update())
    if not orders:
        raise ValidationError(_("Nothing to settle for %(name)s.") % {"name": rider.name})
    warehouse = warehouse or _default_warehouse(company)
    if warehouse is None:
        raise ValidationError(_("Add a stock location first."))
    record = DeliveryHandover.objects.create(company=company, rider=rider, received_by=user, orders_count=len(orders))
    cash = card = Decimal("0")
    for order in orders:
        if order.status != "paid":
            if not order.lines.exists():
                raise ValidationError(_("%(order)s has no items.") % {"order": order.order_number})
            method = "card" if order.collect_method == "card" else "cash"
            invoice = services.settle_order(company=company, user=user, order=order, warehouse=warehouse,
                                            date=timezone.localdate(), payments=method)
            if method == "card":
                card += invoice.transaction_total
            else:
                cash += invoice.transaction_total
        order.handover = record
        order.save(update_fields=["handover"])
    record.cash, record.card = cash, card
    record.save(update_fields=["cash", "card"])
    return record


def _wa(phone, country, text):
    from apps.sales.sharing import normalise_phone
    number = normalise_phone(phone, country)
    return f"https://wa.me/{number}?text={quote(text)}" if number else ""


def customer_whatsapp(order):
    """“Your order is on the way” message for the customer, with the rider's name and number."""
    company = order.company
    name = (order.customer.name if order.customer else "") or ""
    lines = [_("Hi %(name)s,") % {"name": name} if name else _("Hello,"),
             _("Your order %(order)s from %(shop)s is on the way.") % {"order": order.order_number, "shop": company.name}]
    if order.rider:
        lines.append(_("Rider: %(name)s · %(phone)s") % {"name": order.rider.name, "phone": order.rider.phone})
    amount = to_collect(order)
    if amount:
        lines.append(_("Amount to pay: %(amount)s") % {"amount": f"{company.default_currency} {amount:.2f}"})
    return _wa(order.delivery_phone or (order.customer.phone if order.customer else ""), company.country, "\n".join(lines))


def rider_whatsapp(rider, link):
    text = _("Your delivery page (keep this link private): %(url)s") % {"url": link}
    return _wa(rider.phone, rider.company.country, text)


def maps_url(address):
    return f"https://www.google.com/maps/search/?api=1&query={quote(address)}" if address else ""


def rider_orders(rider):
    """What the rider's own page shows: their open orders and today's delivered ones."""
    today = timezone.localdate()
    return (RestaurantOrder.objects.for_company(rider.company).filter(rider=rider).exclude(status="cancelled")
            .filter(Q(delivery_status__in=("assigned", "out")) | Q(delivery_status="delivered", delivered_at__date=today))
            .select_related("customer").prefetch_related("lines__product").order_by("delivery_status", "created_at"))


def report(company, start, end):
    """Per rider and per area, for delivered/failed orders in [start, end]."""
    qs = (RestaurantOrder.objects.for_company(company).filter(channel="delivery", rider__isnull=False)
          .exclude(status="cancelled").filter(created_at__date__gte=start, created_at__date__lte=end)
          .select_related("rider", "zone").prefetch_related("lines__product"))
    riders, zones = {}, {}
    for o in qs:
        r = riders.setdefault(o.rider_id, {"rider": o.rider, "delivered": 0, "failed": 0, "cash": Decimal("0"),
                                           "card": Decimal("0"), "fees": Decimal("0"), "minutes": [], "value": Decimal("0")})
        if o.delivery_status == "delivered":
            r["delivered"] += 1
            r["value"] += o.total
            if o.collect_method in ("cash", "card"):
                r[o.collect_method] += o.total
            r["fees"] += sum((l.total for l in o.lines.all() if l.product.sku == FEE_SKU), Decimal("0"))
            if o.dispatched_at and o.delivered_at:
                r["minutes"].append(max(0, (o.delivered_at - o.dispatched_at).total_seconds() / 60))
            z = zones.setdefault(o.zone.name if o.zone else _("No area"), {"orders": 0, "value": Decimal("0")})
            z["orders"] += 1
            z["value"] += o.total
        elif o.delivery_status == "failed":
            r["failed"] += 1
    rows = []
    for r in riders.values():
        r["avg_minutes"] = round(sum(r["minutes"]) / len(r["minutes"])) if r["minutes"] else None
        rows.append(r)
    rows.sort(key=lambda r: -r["delivered"])
    return rows, sorted(zones.items(), key=lambda kv: -kv[1]["orders"])


def late(order):
    """On the way for longer than the area's usual time (or 45 minutes)."""
    if order.delivery_status != "out" or not order.dispatched_at:
        return False
    limit = order.zone.minutes if order.zone and order.zone.minutes else 45
    return timezone.now() - order.dispatched_at > timedelta(minutes=limit)

