"""
Offline POS support: the data a device needs to keep selling without
internet, and the idempotent sync that turns offline bills into real orders.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.inventory.models import Product, Warehouse

from . import services
from .models import (
    DiningTable, MenuModifier, OfflineOrderSync, RestaurantMenuItem, RestaurantOrder, RestaurantOrderLine,
    RestaurantProfile,
)

MAX_LINES = 300


def bootstrap(company):
    profile = RestaurantProfile.objects.for_company(company).first()
    items = (RestaurantMenuItem.objects.for_company(company).filter(product__is_active=True)
             .select_related("product", "product__category")
             .prefetch_related("modifier_groups__options__modifier").order_by("sort_order", "product__name"))
    categories = {}
    menu = []
    for item in items:
        product = item.product
        if product.category_id:
            categories[product.category_id] = product.category.name
        menu.append({
            "product_id": product.id, "name": product.name, "sku": product.sku, "price": f"{product.selling_price:.2f}",
            "category_id": product.category_id, "description": item.description, "image": item.image.url if item.image else "",
            "veg": item.is_vegetarian, "featured": item.is_featured, "available": item.is_available,
            "minutes": item.preparation_minutes,
            "groups": [{
                "name": g.name, "min": max(g.min_selections, 1 if g.is_required else 0), "max": g.max_selections,
                "options": [{"id": o.modifier_id, "name": o.modifier.name, "price": f"{o.modifier.price_delta:.2f}"}
                            for o in g.options.all() if o.modifier.is_active],
            } for g in item.modifier_groups.all() if g.is_active],
        })
    return {
        "company": {"id": company.id, "name": company.name, "address": company.address, "phone": company.phone,
                    "currency": company.default_currency, "vat_number": getattr(company, "vat_number", "")},
        "tax_percent": f"{(profile.tax_percent if profile else Decimal('0')):.2f}",
        "service_charge_percent": f"{(profile.service_charge_percent if profile else Decimal('0')):.2f}",
        "categories": [{"id": k, "name": v} for k, v in sorted(categories.items(), key=lambda kv: kv[1])],
        "items": menu,
        "tables": [{"id": t.id, "name": t.name, "area": t.area.name, "capacity": t.capacity}
                   for t in DiningTable.objects.for_company(company).filter(is_active=True).select_related("area").order_by("area__name", "name")],
        "generated_at": timezone.now().isoformat(),
    }


def _money(value, field):
    try:
        amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Invalid {field}.")
    if amount < 0:
        raise ValidationError(f"{field} cannot be negative.")
    return amount


def _when(value):
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        return timezone.now()
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def sync_offline_order(*, company, user, payload):
    """
    Upserts one offline bill. Safe to call repeatedly with the same or a newer
    snapshot of the bill: only lines not seen before are added, and payment is
    booked once. Returns the OfflineOrderSync row.
    """
    import uuid
    try:
        client_id = uuid.UUID(str(payload.get("client_id")))
    except ValueError:
        raise ValidationError("Missing bill id.")
    lines = payload.get("lines") or []
    if not isinstance(lines, list) or len(lines) > MAX_LINES:
        raise ValidationError("Invalid bill lines.")
    channel = payload.get("channel") if payload.get("channel") in dict(RestaurantOrder.CHANNELS) else "takeaway"

    with transaction.atomic():
        record, _ = OfflineOrderSync.objects.select_for_update().get_or_create(
            company=company, client_id=client_id,
            defaults={"offline_number": str(payload.get("offline_number", ""))[:40],
                      "device_created_at": _when(payload.get("created_at")), "payload": payload, "synced_by": user},
        )
        record.payload = payload
        order = record.order
        if order is not None and order.status in {"paid", "cancelled"}:
            record.save(update_fields=["payload", "updated_at"])
            return record

        if order is None:
            table = None
            if channel == "dine_in" and payload.get("table_id"):
                table = DiningTable.objects.for_company(company).filter(id=payload["table_id"]).first()
            if channel == "dine_in" and table is None:
                channel = "takeaway"  # table was deleted meanwhile; keep the sale
            order = services.create_order(company=company, channel=channel, table=table, waiter=user,
                                          guests=int(payload.get("guests") or 0))
            order.tax_percent = _money(payload.get("tax_percent"), "tax")
            order.save(update_fields=["tax_percent"])
            record.order = order

        seen = set(record.synced_line_ids)
        sent_ids = set(payload.get("sent_line_ids") or [])
        products = {p.id: p for p in Product.objects.for_company(company).filter(id__in=[l.get("product_id") for l in lines])}
        for line in lines:
            line_id = str(line.get("id") or "")
            if not line_id or line_id in seen:
                if line_id in sent_ids:
                    order.lines.filter(offline_line_id=line_id, sent_at__isnull=True).update(sent_at=timezone.now())
                continue
            product = products.get(line.get("product_id"))
            if product is None:
                raise ValidationError(f"Menu item #{line.get('product_id')} no longer exists.")
            modifiers = list(MenuModifier.objects.for_company(company).filter(id__in=line.get("modifier_ids") or []))
            created = services.add_order_line(
                company=company, order=order, product=product,
                quantity=Decimal(str(line.get("quantity") or "1")), unit_price=_money(line.get("unit_price"), "price"),
                notes=str(line.get("notes") or "")[:255], modifiers=modifiers, already_sold=True,
            )
            created.offline_line_id = line_id
            if line_id in sent_ids:
                created.sent_at = _when(line.get("sent_at"))  # printed on the device's kitchen printer
            created.save(update_fields=["offline_line_id", "sent_at"])
            seen.add(line_id)
        record.synced_line_ids = sorted(seen)
        if order.lines.filter(sent_at__isnull=False).exists() and order.status in {"draft", "held"}:
            order.status = "kitchen"
            order.save(update_fields=["status"])

        record.status, record.error = "synced", ""
        if payload.get("paid"):
            order.service_charge = _money(payload.get("service_charge"), "service charge")
            order.tip_amount = _money(payload.get("tip_amount"), "tip")
            order.discount_amount = _money(payload.get("discount_amount"), "discount")
            order.save(update_fields=["service_charge", "tip_amount", "discount_amount"])
            payments = [{"method": p.get("method") if p.get("method") in {"cash", "card", "bank"} else "cash",
                         "amount": _money(p.get("amount"), "payment"), "reference": f"Offline {record.offline_number}"}
                        for p in payload.get("payments") or [] if _money(p.get("amount"), "payment") > 0]
            warehouse = Warehouse.objects.for_company(company).filter(is_active=True).order_by("-is_default", "id").first()
            try:
                services.settle_order(company=company, user=user, order=order, warehouse=warehouse,
                                      date=timezone.localdate(_when(payload.get("paid_at"))), payments=payments)
            except ValidationError as exc:
                # The customer already paid; keep the order open and ask a manager to finish it.
                record.status, record.error = "attention", " ".join(exc.messages)[:255]
        record.save()
    services.broadcast_kitchen_update(company, "offline_sync")
    return record


def result(record):
    order = record.order
    return {
        "client_id": str(record.client_id), "status": record.status, "error": record.error,
        "order_id": order.id if order else None, "order_number": order.order_number if order else "",
        "order_status": order.status if order else "",
        "invoice_number": order.invoice.invoice_number if order and order.invoice_id else "",
    }
