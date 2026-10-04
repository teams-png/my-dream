from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.customers.services import get_or_create_walkin_customer
from apps.inventory.models import Product, Unit
from apps.inventory.services import record_stock_movement
from apps.sales.services import create_invoice, record_customer_payment
from apps.tenants.services import next_counter_value

from .models import (
    DeliveryOrderImport, FoodWaste, KitchenStation, RestaurantMenuItem, KitchenTicket, RestaurantOrder, RestaurantOrderLine,
    RestaurantOrderLineModifier, RestaurantPaymentSplit, RestaurantProfile, RestaurantShift,
)


def validate_modifier_selections(*, company, product, modifiers):
    try:
        menu_item = RestaurantMenuItem.objects.for_company(company).get(product=product)
    except RestaurantMenuItem.DoesNotExist:
        return
    selected_ids = {m.id for m in modifiers}
    groups = list(menu_item.modifier_groups.filter(is_active=True).prefetch_related("options"))
    allowed_all = {x.modifier_id for group in groups for x in group.options.all()}
    if selected_ids - allowed_all:
        raise ValidationError("One or more add-ons are not valid for this menu item.")
    for group in groups:
        allowed = {x.modifier_id for x in group.options.all()}
        count = len(selected_ids & allowed)
        minimum = max(group.min_selections, 1 if group.is_required else 0)
        if count < minimum or count > group.max_selections:
            raise ValidationError(f"Choose {minimum} to {group.max_selections} option(s) for {group.name}.")


def broadcast_kitchen_update(company, event="refresh"):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(f"kitchen_{company.id}", {"type": "kitchen.update", "event": event})
    except Exception:
        # KDS retains its timed HTTP refresh fallback if Redis/WebSockets are unavailable.
        return


def verify_delivery_webhook(integration, body, signature):
    import hashlib, hmac
    secret = integration.get_secret("webhook_secret")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


@transaction.atomic
def import_delivery_order(*, integration, payload):
    from apps.customers.models import Customer
    company = integration.company
    external_id = str(payload.get("external_order_id") or payload.get("id") or "")
    if not external_id:
        raise ValidationError("external_order_id is required.")
    log, created = DeliveryOrderImport.objects.get_or_create(
        company=company, integration=integration, external_order_id=external_id,
        defaults={"payload": payload},
    )
    if not created:
        return log
    try:
        customer_data = payload.get("customer") or {}
        phone = customer_data.get("phone", "")
        customer = Customer.objects.for_company(company).filter(phone=phone).first() if phone else None
        if not customer:
            customer = Customer.objects.create(company=company, name=customer_data.get("name") or f"{integration.get_provider_display()} Customer", phone=phone, address=customer_data.get("address", ""))
        order = create_order(
            company=company, channel="delivery", customer=customer,
            delivery_address=customer_data.get("address") or payload.get("delivery_address", ""),
            delivery_phone=phone,
        )
        for item in payload.get("items", []):
            product = Product.objects.for_company(company).filter(sku=item.get("sku"), is_active=True).first()
            if not product:
                raise ValidationError(f"Unknown menu SKU: {item.get('sku')}")
            add_order_line(company=company, order=order, product=product,
                           quantity=item.get("quantity", 1), unit_price=item.get("unit_price"),
                           notes=item.get("notes", ""))
        if integration.auto_accept_orders:
            send_to_kitchen(company=company, order=order)
        log.restaurant_order = order; log.status = "imported"; log.save(update_fields=["restaurant_order", "status"])
        integration.last_sync_at = timezone.now(); integration.last_error = ""; integration.save(update_fields=["last_sync_at", "last_error"])
    except Exception as exc:
        log.status = "failed"; log.error_message = str(exc); log.save(update_fields=["status", "error_message"])
        integration.last_error = str(exc); integration.save(update_fields=["last_error"])
    return log


@transaction.atomic
def open_shift(*, company, user, opening_cash=0):
    if RestaurantShift.objects.for_company(company).filter(status="open").exists():
        raise ValidationError("A restaurant shift is already open.")
    return RestaurantShift.objects.create(company=company, opened_by=user, opening_cash=opening_cash)


@transaction.atomic
def close_shift(*, company, user, shift, actual_cash):
    if shift.company_id != company.id or shift.status != "open":
        raise ValidationError("This shift cannot be closed.")
    cash_sales = sum((p.amount for p in RestaurantPaymentSplit.objects.for_company(company).filter(
        order__shift=shift, order__status="paid", method="cash",
    )), Decimal("0"))
    shift.expected_cash = shift.opening_cash + cash_sales
    shift.actual_cash = Decimal(actual_cash)
    shift.variance = shift.actual_cash - shift.expected_cash
    shift.closed_by = user
    shift.closed_at = timezone.now()
    shift.status = "closed"
    shift.save(update_fields=["expected_cash", "actual_cash", "variance", "closed_by", "closed_at", "status"])
    return shift


def _restaurant_tax_percent(company):
    profile = RestaurantProfile.objects.for_company(company).first()
    return profile.tax_percent if profile else Decimal("0")


EDITABLE_ORDER_STATUSES = {"draft", "held", "kitchen", "ready", "served"}


@transaction.atomic
def create_order(*, company, channel, table=None, customer=None, waiter=None, shift=None,
                 delivery_address="", delivery_phone="", delivery_driver=None, guests=0):
    if channel == "dine_in" and table is None:
        raise ValidationError("A table is required for dine-in orders.")
    if channel == "delivery" and not delivery_address:
        raise ValidationError("A delivery address is required.")
    order = RestaurantOrder.objects.create(
        company=company, order_number=f"ORD-{next_counter_value(company, 'restaurant_order'):06d}",
        channel=channel, table=table, customer=customer, waiter=waiter, shift=shift,
        delivery_address=delivery_address, delivery_phone=delivery_phone, delivery_driver=delivery_driver,
        guests=guests or 0, tax_percent=_restaurant_tax_percent(company),
    )
    if table:
        table.status = "occupied"; table.save(update_fields=["status"])
    return order


@transaction.atomic
def add_order_line(*, company, order, product, quantity=1, unit_price=None, notes="", modifiers=(), already_sold=False):
    """already_sold=True is used when syncing an offline bill: the sale has
    already happened, so today's menu hours and add-on rules must not block it."""
    if order.company_id != company.id or product.company_id != company.id:
        raise ValidationError("Order and product must belong to the active company.")
    if order.status not in EDITABLE_ORDER_STATUSES:
        raise ValidationError("Items cannot be added to a paid or cancelled order.")
    modifiers = list(modifiers)
    if any(m.company_id != company.id for m in modifiers):
        raise ValidationError("Add-ons must belong to the active company.")
    if not already_sold:
        try:
            menu_item = RestaurantMenuItem.objects.for_company(company).get(product=product)
            if not menu_item.is_orderable_now():
                raise ValidationError("This menu item is not available at the current time.")
        except RestaurantMenuItem.DoesNotExist:
            pass
        validate_modifier_selections(company=company, product=product, modifiers=modifiers)
    line = RestaurantOrderLine.objects.create(
        company=company, order=order, product=product, quantity=quantity,
        unit_price=unit_price if unit_price is not None else product.selling_price, notes=notes,
    )
    for modifier in modifiers:
        RestaurantOrderLineModifier.objects.create(
            company=company, line=line, modifier=modifier, price_delta=modifier.price_delta,
        )
    return line


@transaction.atomic
def update_order_line_quantity(*, company, line, quantity):
    if line.company_id != company.id or line.order.status not in EDITABLE_ORDER_STATUSES or line.sent_at:
        raise ValidationError("This item was already sent to the kitchen and cannot be changed.")
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        line.delete()
        return None
    line.quantity = quantity
    line.save(update_fields=["quantity"])
    return line


@transaction.atomic
def remove_order_line(*, company, line):
    if line.company_id != company.id or line.order.status not in EDITABLE_ORDER_STATUSES or line.sent_at:
        raise ValidationError("This item was already sent to the kitchen and cannot be removed.")
    line.delete()


def set_order_held(*, company, order, held=True):
    if order.company_id != company.id or order.status not in {"draft", "held"}:
        raise ValidationError("This order cannot be held/resumed.")
    order.status = "held" if held else "draft"
    order.save(update_fields=["status"])
    return order


@transaction.atomic
def send_to_kitchen(*, company, order):
    unsent = order.lines.filter(sent_at__isnull=True)
    if order.company_id != company.id or order.status not in EDITABLE_ORDER_STATUSES or not unsent.exists():
        raise ValidationError("There are no new items to send to the kitchen.")
    kitchen_round = (order.kitchen_tickets.aggregate(m=models.Max("kitchen_round"))["m"] or 0) + 1
    stations = KitchenStation.objects.for_company(company).filter(is_active=True)
    relevant = []
    order_category_ids = set(unsent.exclude(product__category=None).values_list("product__category_id", flat=True))
    for station in stations.prefetch_related("categories"):
        category_ids = set(station.categories.values_list("id", flat=True))
        if not category_ids or category_ids & order_category_ids:
            relevant.append(station)
    if not relevant:
        relevant = [None]
    tickets = [KitchenTicket.objects.create(
        company=company, order=order, station=station,
        ticket_number=f"KOT-{next_counter_value(company, 'restaurant_kot'):06d}",
        kitchen_round=kitchen_round, priority=1 if kitchen_round > 1 else 0,
    ) for station in relevant]
    unsent.update(kitchen_round=kitchen_round, sent_at=timezone.now())
    order.status = "kitchen"; order.save(update_fields=["status"])
    broadcast_kitchen_update(company, "new_order")
    return tickets[0]


@transaction.atomic
def record_food_waste(*, company, user, ingredient, warehouse, quantity, reason, notes=""):
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError("Waste quantity must be greater than zero.")
    if ingredient.company_id != company.id or warehouse.company_id != company.id:
        raise ValidationError("Ingredient and warehouse must belong to the active company.")
    if ingredient.current_stock(warehouse) < quantity:
        raise ValidationError("Waste quantity exceeds available stock.")
    waste = FoodWaste.objects.create(
        company=company, ingredient=ingredient, warehouse=warehouse, quantity=quantity,
        reason=reason, notes=notes, recorded_by=user,
    )
    record_stock_movement(
        company=company, product=ingredient, warehouse=warehouse, quantity=-quantity,
        reason="adjustment", reference=f"FOOD-WASTE-{waste.id}",
    )
    return waste


def update_kitchen_status(*, company, ticket, status):
    next_status = {"queued": "preparing", "preparing": "ready", "ready": "served"}
    if ticket.company_id != company.id or next_status.get(ticket.status) != status:
        raise ValidationError("Invalid kitchen ticket status.")
    ticket.status = status
    fields = ["status"]
    if status == "preparing": ticket.started_at = timezone.now(); fields.append("started_at")
    if status == "ready": ticket.ready_at = timezone.now(); fields.append("ready_at")
    ticket.save(update_fields=fields)
    if status in {"ready", "served"} and not ticket.order.kitchen_tickets.exclude(status__in=[status, "served"]).exists():
        ticket.order.status = status
        ticket.order.save(update_fields=["status"])
    broadcast_kitchen_update(company, "status_changed")
    return ticket


@transaction.atomic
def cancel_order(*, company, user, order, reason):
    if order.company_id != company.id:
        raise ValidationError("This order does not belong to the active company.")
    if order.status == "paid":
        raise ValidationError("Paid orders must be processed through the audited sales return/refund workflow.")
    if order.status == "cancelled":
        raise ValidationError("This order is already cancelled.")
    if not reason or not reason.strip():
        raise ValidationError("A cancellation reason is required.")
    previous_status = order.status
    order.status = "cancelled"
    order.cancelled_reason = reason.strip()
    order.cancelled_by = user
    order.cancelled_at = timezone.now()
    order.save(update_fields=["status", "cancelled_reason", "cancelled_by", "cancelled_at"])
    if order.table:
        order.table.status = "available"
        order.table.save(update_fields=["status"])
    from apps.audit.services import log_action
    log_action(company=company, user=user, action="cancel", model_name="RestaurantOrder", object_id=order.id,
               changes={"status": [previous_status, "cancelled"], "reason": reason.strip()})
    broadcast_kitchen_update(company, "order_cancelled")
    return order


@transaction.atomic
def merge_orders(*, company, target, source):
    if target.company_id != company.id or source.company_id != company.id or target.id == source.id:
        raise ValidationError("Orders must be different and belong to the active company.")
    if target.status in {"paid", "cancelled"} or source.status in {"paid", "cancelled"}:
        raise ValidationError("Paid or cancelled orders cannot be merged.")
    # Lines already cooked for the source order keep their sent flag but are not
    # shown on the target's kitchen tickets (round 0).
    source.lines.filter(sent_at__isnull=False).update(order=target, kitchen_round=0)
    source.lines.update(order=target)
    source.status = "cancelled"; source.save(update_fields=["status"])
    if source.table:
        source.table.status = "available"; source.table.save(update_fields=["status"])
    return target


@transaction.atomic
def transfer_table(*, company, order, table):
    if order.company_id != company.id or table.company_id != company.id:
        raise ValidationError("Order and table must belong to the active company.")
    if order.status in {"paid", "cancelled"}:
        raise ValidationError("Paid or cancelled orders cannot be moved.")
    if order.table_id == table.id:
        raise ValidationError("The order is already on this table.")
    busy = RestaurantOrder.objects.for_company(company).filter(table=table).exclude(status__in=["paid", "cancelled"]).exists()
    if busy or not table.is_active:
        raise ValidationError(f"Table {table.name} is not free.")
    old = order.table
    order.table = table
    if order.channel != "dine_in":
        order.channel = "dine_in"
    order.save(update_fields=["table", "channel"])
    table.status = "occupied"; table.save(update_fields=["status"])
    if old and not RestaurantOrder.objects.for_company(company).filter(table=old).exclude(status__in=["paid", "cancelled"]).exists():
        old.status = "available"; old.save(update_fields=["status"])
    broadcast_kitchen_update(company, "table_changed")
    return order


@transaction.atomic
def split_order(*, company, order, line_ids):
    if order.company_id != company.id or order.status in {"paid", "cancelled"}:
        raise ValidationError("This order cannot be split.")
    new_order = create_order(company=company, channel=order.channel, customer=order.customer,
                             table=order.table, waiter=order.waiter, shift=order.shift,
                             delivery_address=order.delivery_address, delivery_phone=order.delivery_phone,
                             delivery_driver=order.delivery_driver)
    moved = order.lines.filter(id__in=line_ids)
    if not moved.exists() or moved.count() == order.lines.count():
        raise ValidationError("Select some, but not all, lines to split.")
    moved.update(order=new_order)
    new_order.tax_percent = order.tax_percent
    fields = ["tax_percent"]
    if order.status in {"kitchen", "ready", "served"}:
        new_order.status = order.status; fields.append("status")
    new_order.save(update_fields=fields)
    return new_order


def _charge_product(company, sku, name):
    unit, _ = Unit.objects.get_or_create(company=company, name="charge")
    product, _ = Product.objects.get_or_create(company=company, sku=sku, defaults={
        "name": name, "unit": unit, "is_stock_tracked": False, "tracking_type": "none",
    })
    return product


@transaction.atomic
def settle_order(*, company, user, order, warehouse, date, payments):
    if order.company_id != company.id or order.status in {"paid", "cancelled"} or not order.lines.exists():
        raise ValidationError("This order cannot be billed.")
    customer = order.customer or get_or_create_walkin_customer(company)
    invoice_lines = [{"product": line.product, "quantity": line.quantity,
                      "unit_price": line.unit_price + line.modifier_total} for line in order.lines.select_related("product")]
    if order.service_charge:
        invoice_lines.append({"product": _charge_product(company, "RESTAURANT-SERVICE-CHARGE", "Restaurant Service Charge"), "quantity": 1, "unit_price": order.service_charge})
    if order.tip_amount:
        invoice_lines.append({"product": _charge_product(company, "RESTAURANT-TIP", "Restaurant Tip"), "quantity": 1, "unit_price": order.tip_amount})
    invoice = create_invoice(
        company=company, user=user, customer=customer, date=date, warehouse=warehouse,
        lines=invoice_lines, discount_amount=order.discount_amount,
        tax_rate=order.tax_percent / Decimal("100"),
        discount_reason="Restaurant order discount" if order.discount_amount else "",
        discount_approved_by=user if order.discount_amount else None,
    )
    if isinstance(payments, str):  # one method for the whole bill (quick sale counter)
        payments = [{"method": payments, "amount": invoice.transaction_total}]
    payment_total = sum((Decimal(str(p["amount"])) for p in payments), Decimal("0"))
    if payment_total != invoice.transaction_total:
        raise ValidationError("Split payment total must equal the order total.")
    for payment in payments:
        RestaurantPaymentSplit.objects.create(company=company, order=order, method=payment["method"], amount=payment["amount"], reference=payment.get("reference", ""))
        record_customer_payment(company=company, user=user, customer=customer, invoice=invoice,
                                amount=payment["amount"], date=date, method=payment["method"])
    for line in order.lines.select_related("product"):
        for recipe in line.product.restaurant_recipe.select_related("ingredient_product"):
            required = recipe.quantity * line.quantity
            if recipe.ingredient_product.current_stock(warehouse) < required:
                raise ValidationError(f"Insufficient ingredient stock: {recipe.ingredient_product.name}.")
            record_stock_movement(company=company, product=recipe.ingredient_product, warehouse=warehouse,
                                  quantity=-required, reason="sale", reference=invoice.invoice_number)
    order.invoice = invoice; order.status = "paid"; order.save(update_fields=["invoice", "status"])
    if order.table:
        order.table.status = "cleaning"; order.table.save(update_fields=["status"])
    return invoice
