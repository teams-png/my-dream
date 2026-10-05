"""
Website ordering: a customer adds menu items to a cart on the restaurant's website (BookPilot website or the
WordPress plugin) and sends the order. It arrives in BookPilot as a held restaurant order in the
"Online orders" inbox; staff accept it (it goes to the kitchen) or reject it. Prices always come from
BookPilot, never from the website.
"""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import OnlineOrder, RestaurantMenuItem, RestaurantProfile, RestaurantShift
from . import services

MAX_LINES = 40
MAX_QTY = 50
FEE_SKU = "DELIVERY-FEE"


def profile_for(company):
    profile, _ = RestaurantProfile.objects.get_or_create(company=company)
    return profile


def is_restaurant(company):
    from apps.modules.catalog import business_group
    return business_group(company.business_type.code) == "restaurant"


def needs_choice(menu_item):
    """Items with a required add-on group can only be ordered at the counter (the website cart has no add-ons)."""
    return any(g.is_required or g.min_selections for g in menu_item.modifier_groups.all() if g.is_active)


def config(company):
    """What the website cart needs to know. None when website ordering is off."""
    if not is_restaurant(company):
        return None
    profile = RestaurantProfile.objects.for_company(company).first()
    if not profile or not profile.web_orders_enabled or not (profile.web_pickup or profile.web_delivery):
        return None
    return {"enabled": True, "open": not profile.web_paused, "pickup": profile.web_pickup,
            "delivery": profile.web_delivery, "delivery_fee": f"{profile.delivery_charge:.2f}",
            "minimum": f"{profile.delivery_minimum:.2f}", "ready_minutes": profile.web_ready_minutes,
            "note": profile.web_note, "currency": company.default_currency}


def _clean_phone(value):
    phone = re.sub(r"[^\d+ ]", "", str(value or "")).strip()[:30]
    if len(re.sub(r"\D", "", phone)) < 7:
        raise ValidationError("Enter a phone number we can call.")
    return phone


@transaction.atomic
def place(company, data, source=""):
    """data: {name, phone, mode, address, note, items: [{id, qty, note}]} → OnlineOrder."""
    from apps.customers.models import Customer
    cfg = config(company)
    if not cfg:
        raise ValidationError("Online ordering is switched off.")
    if not cfg["open"]:
        raise ValidationError("Sorry, we are not taking online orders right now. Please call us.")
    profile = profile_for(company)
    name = str(data.get("name") or "").strip()[:150]
    if len(name) < 2:
        raise ValidationError("Enter your name.")
    phone = _clean_phone(data.get("phone"))
    mode = data.get("mode") if data.get("mode") in ("pickup", "delivery") else ("pickup" if profile.web_pickup else "delivery")
    if (mode == "pickup" and not profile.web_pickup) or (mode == "delivery" and not profile.web_delivery):
        raise ValidationError("This order type is not available.")
    address = str(data.get("address") or "").strip()[:500]
    if mode == "delivery" and len(address) < 5:
        raise ValidationError("Enter the delivery address.")
    note = str(data.get("note") or "").strip()[:255]

    rows = data.get("items") or []
    if not isinstance(rows, list) or not rows:
        raise ValidationError("Your cart is empty.")
    if len(rows) > MAX_LINES:
        raise ValidationError("Too many items in one order. Please call us for big orders.")
    wanted = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("Your cart is not valid. Please refresh the page.")
        try:
            pid, qty = int(row.get("id")), int(row.get("qty", 1))
        except (TypeError, ValueError):
            raise ValidationError("Your cart is not valid. Please refresh the page.")
        if qty < 1 or qty > MAX_QTY:
            raise ValidationError(f"You can order 1 to {MAX_QTY} of each item.")
        wanted.append((pid, qty, str(row.get("note") or "").strip()[:120]))
    menu = {m.product_id: m for m in RestaurantMenuItem.objects.for_company(company).filter(
        product_id__in=[w[0] for w in wanted]).select_related("product").prefetch_related("modifier_groups")}
    subtotal = Decimal("0")
    for pid, qty, _ in wanted:
        item = menu.get(pid)
        if item is None:
            raise ValidationError("An item in your cart is no longer on the menu. Please refresh the page.")
        if not item.is_orderable_now() or needs_choice(item):
            raise ValidationError(f"Sorry, {item.product.name} is not available online right now.")
        subtotal += item.product.selling_price * qty
    fee = profile.delivery_charge if mode == "delivery" else Decimal("0")
    if mode == "delivery" and profile.delivery_minimum and subtotal < profile.delivery_minimum:
        raise ValidationError(f"The minimum order for delivery is {company.default_currency} {profile.delivery_minimum:.2f}.")

    customer = Customer.objects.for_company(company).filter(phone=phone).first()
    if not customer:
        customer = Customer.objects.create(company=company, name=name, phone=phone, address=address if mode == "delivery" else "")
    order = services.create_order(
        company=company, channel="delivery" if mode == "delivery" else "takeaway", customer=customer,
        delivery_address=address if mode == "delivery" else "", delivery_phone=phone,
        shift=RestaurantShift.objects.for_company(company).filter(status="open").first())
    for pid, qty, line_note in wanted:
        services.add_order_line(company=company, order=order, product=menu[pid].product, quantity=qty, notes=line_note)
    if fee:
        line = services.add_order_line(company=company, order=order, product=services._charge_product(company, FEE_SKU, "Delivery charge"),
                                       quantity=1, unit_price=fee, notes="Website order")
        line.sent_at = timezone.now()  # never printed on the kitchen ticket
        line.save(update_fields=["sent_at"])
    order.status = "held"
    order.save(update_fields=["status"])
    online = OnlineOrder.objects.create(company=company, order=order, mode=mode, customer_name=name, phone=phone,
                                        address=address if mode == "delivery" else "", note=note, source=source[:120],
                                        total=order.total)
    if profile.web_auto_accept:
        online = accept(online, user=None)
    else:
        _tell_staff(online)
    return online


def _tell_staff(online):
    from apps.notifications.services import notify
    try:
        notify(company=online.company, title=f"New website order {online.order.order_number}",
               message=f"{online.customer_name} · {online.phone} · {online.get_mode_display()} · "
                       f"{online.company.default_currency} {online.total:.2f}",
               idempotency_key=f"online-order:{online.pk}")
    except Exception:  # a mail problem must never lose the order
        pass
    services.broadcast_kitchen_update(online.company, "online_order")


@transaction.atomic
def accept(online, user):
    online = OnlineOrder.objects.select_for_update().select_related("order").get(pk=online.pk)  # double taps
    if online.status != "new":
        raise ValidationError("This order was already handled.")
    order = online.order
    order.status = "draft"
    order.save(update_fields=["status"])
    services.send_to_kitchen(company=online.company, order=order)
    online.status, online.handled_by, online.handled_at = "accepted", user, timezone.now()
    online.save(update_fields=["status", "handled_by", "handled_at"])
    return online


@transaction.atomic
def reject(online, user, reason):
    online = OnlineOrder.objects.select_for_update().select_related("order").get(pk=online.pk)  # double taps
    if online.status != "new":
        raise ValidationError("This order was already handled.")
    reason = (reason or "").strip()[:255] or "The restaurant could not take this order."
    services.cancel_order(company=online.company, user=user, order=online.order, reason=f"Website order rejected: {reason}")
    online.status, online.reject_reason = "rejected", reason
    online.handled_by, online.handled_at = user, timezone.now()
    online.save(update_fields=["status", "reject_reason", "handled_by", "handled_at"])
    return online


def waiting_count(company):
    return OnlineOrder.objects.for_company(company).filter(status="new").count()
