"""
Retail POS checkout, shared by the live till and by offline sales that a
device syncs later. Everything runs in one transaction: if any step fails
(stock, coupon, credit limit...) nothing is saved.
"""
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.customers import services as customer_services
from apps.customers.models import Customer
from apps.inventory.models import Product, Warehouse

from . import services as sales_services
from .models import OfflineSaleSync

WALK_IN = "Walk-in Customer"
LIVE_METHODS = {"cash", "card", "bank", "credit", "installment"}
OFFLINE_METHODS = {"cash", "card", "bank"}
MAX_LINES = 300
MAX_OFFLINE_AGE_DAYS = 60


class PosError(Exception):
    pass


def _warehouse(company, warehouse_id):
    if warehouse_id:
        wh = Warehouse.objects.for_company(company).filter(id=warehouse_id, is_active=True).first()
        if wh is not None:
            return wh
    wh = (Warehouse.objects.for_company(company).filter(is_default=True).first()
          or Warehouse.objects.for_company(company).first())
    if wh is None:
        wh = Warehouse.objects.create(company=company, name="Main", is_default=True)
    return wh


def _message(exc):
    return " ".join(getattr(exc, "messages", None) or [str(exc)])[:255]


def checkout(*, company, user, payload, sale_date=None):
    """Creates the invoice, payment, IMEI and loyalty records for one POS sale."""
    from apps.verticals.mobile_shop.models import MobileInstallmentPlan, MobileUnit

    cart = payload.get("lines") or []
    if not isinstance(cart, list) or not cart:
        raise PosError("Cart is empty.")
    if len(cart) > MAX_LINES:
        raise PosError("Too many lines in one sale.")
    payment_method = payload.get("payment_method") or "cash"
    if payment_method not in LIVE_METHODS:
        raise PosError("Unknown payment method.")
    today = sale_date or timezone.localdate()

    with transaction.atomic():
        customer_id = payload.get("customer_id")
        if customer_id:
            customer = Customer.objects.for_company(company).filter(id=customer_id).first()
            if customer is None:
                raise PosError("Customer not found.")
        else:
            customer, _ = Customer.objects.get_or_create(company=company, name=WALK_IN, defaults={"is_active": True})

        warehouse = _warehouse(company, payload.get("warehouse_id"))
        products = {p.id: p for p in Product.objects.for_company(company).filter(
            id__in=[item.get("product_id") for item in cart if isinstance(item, dict)])}
        lines, units = [], []
        for item in cart:
            product = products.get(item.get("product_id")) if isinstance(item, dict) else None
            if product is None:
                raise PosError(f"Product #{item.get('product_id') if isinstance(item, dict) else '?'} no longer exists.")
            try:
                quantity = Decimal(str(item.get("quantity", 1))).quantize(Decimal("0.001"))
                unit_price = Decimal(str(item.get("unit_price"))).quantize(Decimal("0.01"))
            except (InvalidOperation, TypeError, ValueError):
                raise PosError(f"Bad quantity/price for {product.name}.")
            if quantity <= 0:
                raise PosError(f"Quantity for {product.name} must be positive.")
            if unit_price < 0:
                raise PosError(f"Price for {product.name} cannot be negative.")
            unit_id = item.get("mobile_unit_id")
            if unit_id:
                if quantity != 1:
                    raise PosError("Each IMEI handset must be billed as quantity 1.")
                unit = MobileUnit.objects.select_for_update().for_company(company).filter(id=unit_id, product=product).first()
                if unit is None:
                    raise PosError(f"IMEI unit for {product.name} not found.")
                if unit.status != "in_stock":
                    raise PosError(f"IMEI {unit.imei} is no longer in stock.")
                units.append((unit, unit_price))
            lines.append({"product": product, "quantity": quantity, "unit_price": unit_price})

        subtotal = sum((line["quantity"] * line["unit_price"] for line in lines), Decimal("0"))
        coupon_code = (payload.get("coupon_code") or "").strip()
        coupon, discount_amount = None, Decimal("0")
        if coupon_code:
            coupon, discount_amount = sales_services.validate_coupon(
                company=company, code=coupon_code, subtotal=subtotal, date=today)

        invoice = sales_services.create_invoice(
            company=company, user=user, customer=customer, date=today, lines=lines, warehouse=warehouse,
            discount_amount=discount_amount, coupon_code=coupon_code,
        )
        deferred = payment_method in {"credit", "installment"}
        amount_paid = invoice.total
        if deferred:
            if customer.name == WALK_IN:
                raise PosError("Select a customer for credit or instalment sales.")
            try:
                amount_paid = Decimal(str(payload.get("amount_paid") or 0))
            except InvalidOperation:
                raise PosError("Invalid paid amount.")
            if amount_paid < 0 or amount_paid > invoice.total:
                raise PosError("Paid amount must be between zero and invoice total.")
        if amount_paid:
            method = (payload.get("deposit_method") or "cash") if deferred else payment_method
            sales_services.record_customer_payment(
                company=company, user=user, customer=customer, amount=amount_paid, date=today,
                invoice=invoice, method=method if method in OFFLINE_METHODS else "cash",
            )
        if deferred and customer.credit_limit:
            from apps.collections.services import customer_credit_status
            credit = customer_credit_status(company, customer)
            if credit["over_limit"]:
                raise PosError(
                    f"Credit limit exceeded. Limit {customer.credit_limit}; outstanding {credit['outstanding']}.")
        if payment_method == "installment":
            due_raw = payload.get("next_due_date")
            due_date = (parse_date(due_raw) if due_raw else None) or today + timedelta(days=30)
            try:
                count = max(1, int(payload.get("installment_count") or 1))
            except (TypeError, ValueError):
                raise PosError("Invalid number of instalments.")
            MobileInstallmentPlan.objects.create(
                company=company, invoice=invoice, customer=customer, financed_amount=invoice.total - amount_paid,
                deposit=amount_paid, installment_count=count,
                frequency=payload.get("frequency") if payload.get("frequency") in {"weekly", "monthly"} else "monthly",
                next_due_date=due_date,
            )
        for unit, price in units:
            unit.status, unit.buyer, unit.sold_price = "sold", customer, price
            unit.sold_date, unit.sale_invoice, unit.warehouse = today, invoice, warehouse
            unit.save(update_fields=["status", "buyer", "sold_price", "sold_date", "sale_invoice", "warehouse"])
        if coupon:
            sales_services.redeem_coupon_usage(coupon)
        points_earned = None
        if customer.name != WALK_IN:
            points_earned = customer_services.earn_points(
                company=company, customer=customer, amount_spent=invoice.total, date=today,
                reference=invoice.invoice_number,
            )

    return {
        "invoice_id": invoice.id, "invoice_number": invoice.invoice_number, "total": str(invoice.total),
        "discount_amount": str(discount_amount), "points_earned": points_earned,
        "amount_paid": str(amount_paid), "balance": str(invoice.total - amount_paid),
    }


def live_checkout(*, company, user, payload):
    """
    The till sends a fresh client_id with every sale. If the answer is lost
    (network drop, proxy timeout) the till keeps the sale for offline sync
    under the same id, and this row makes sure it is billed only once.
    """
    try:
        client_id = uuid.UUID(str(payload.get("client_id")))
    except ValueError:
        return checkout(company=company, user=user, payload=payload)
    with transaction.atomic():
        record, created = OfflineSaleSync.objects.select_for_update().get_or_create(
            company=company, client_id=client_id,
            defaults={"channel": "live", "offline_number": str(payload.get("offline_number", ""))[:40],
                      "device_created_at": timezone.now(), "synced_by": user},
        )
        if not created and record.invoice_id:
            return (record.payload or {}).get("result") or {
                "invoice_id": record.invoice_id, "invoice_number": record.invoice.invoice_number,
                "total": str(record.invoice.total)}
        if not created:
            raise PosError("This sale is already waiting in the offline queue.")
        data = checkout(company=company, user=user, payload=payload)
        record.invoice_id, record.payload = data["invoice_id"], {"result": data}
        record.save(update_fields=["invoice", "payload", "updated_at"])
    return data


def _device_time(value):
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        return timezone.now()
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _offline_date(created_at):
    """The day the customer actually paid, within reason (a device clock can be wrong)."""
    today = timezone.localdate()
    day = timezone.localdate(created_at)
    if day > today or day < today - timedelta(days=MAX_OFFLINE_AGE_DAYS):
        return today
    return day


def sync_offline_sale(*, company, user, payload):
    """
    Turns one offline sale into an invoice exactly once. A sale the server
    cannot accept (item sold out, IMEI already sold...) is kept as "needs
    attention" with the reason, so a manager can fix it: the customer has
    already paid.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Invalid sale.")
    try:
        client_id = uuid.UUID(str(payload.get("client_id")))
    except ValueError:
        raise ValidationError("Missing sale id.")
    created_at = _device_time(payload.get("created_at"))

    with transaction.atomic():
        record, _ = OfflineSaleSync.objects.select_for_update().get_or_create(
            company=company, client_id=client_id,
            defaults={"offline_number": str(payload.get("offline_number", ""))[:40], "device_created_at": created_at,
                      "payload": payload, "synced_by": user},
        )
        if record.invoice_id or record.status == "resolved":
            return record
        return _book(record, company=company, user=user, payload=payload)


def _book(record, *, company, user, payload):
    sale = {
        "lines": payload.get("lines") or [], "customer_id": payload.get("customer_id"),
        "warehouse_id": payload.get("warehouse_id"),
        "payment_method": payload.get("payment_method") if payload.get("payment_method") in OFFLINE_METHODS else "cash",
    }
    record.payload = payload
    try:
        result = checkout(company=company, user=user, payload=sale,
                          sale_date=_offline_date(record.device_created_at or timezone.now()))
    except (PosError, ValidationError, ValueError) as exc:
        record.status, record.error = "attention", _message(exc)
    else:
        record.invoice_id = result["invoice_id"]
        record.status, record.error = "synced", ""
    record.synced_by = user
    record.save()
    return record


def retry(record, *, user):
    """Books an attention sale again, e.g. after stock was received."""
    with transaction.atomic():
        record = OfflineSaleSync.objects.select_for_update().get(pk=record.pk)
        if record.invoice_id or record.status == "resolved":
            return record
        return _book(record, company=record.company, user=user, payload=record.payload)


def result(record):
    invoice = record.invoice
    return {
        "client_id": str(record.client_id), "status": record.status, "error": record.error,
        "invoice_id": invoice.id if invoice else None,
        "invoice_number": invoice.invoice_number if invoice else "",
    }
