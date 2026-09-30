from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import StockMovement, ProductBatch, ProductSerial, StockCount, StockCountLine, BatchAlertLog, Warehouse


def _to_date(value):
    if value is None:
        return None
    from datetime import date as _date
    return value if isinstance(value, _date) else parse_date(str(value))


def record_stock_movement(*, company, product, warehouse, quantity, reason, reference="", batch=None, serial=None):
    """
    The only sanctioned write path to stock levels — an append-only ledger
    entry, never a direct mutation of a stored quantity field
    (Phase 0 Section 18 risk: "Treating Product.stock_quantity as the
    source of truth"). `batch`/`serial` are Phase 31 additions, both
    optional and None by default — every pre-Phase-31 call site keeps
    working unchanged, and existing StockMovement history (all NULL on
    these two columns) is untouched.
    """
    return StockMovement.objects.create(
        company=company, product=product, warehouse=warehouse,
        quantity=quantity, reason=reason, reference=reference,
        batch=batch, serial=serial,
    )


# ---------------------------------------------------------------- batches


def create_batch(*, company, product, batch_number, manufacture_date=None, expiry_date=None):
    if product.company_id != company.id:
        raise ValidationError("This product does not belong to the active company.")
    if product.tracking_type != "batch":
        raise ValidationError("This product is not batch-tracked (tracking_type must be 'batch').")

    batch, _ = ProductBatch.objects.get_or_create(
        company=company, product=product, batch_number=batch_number,
        defaults={"manufacture_date": _to_date(manufacture_date), "expiry_date": _to_date(expiry_date)},
    )
    return batch


def receive_batch_stock(*, company, product, warehouse, batch, quantity, reference=""):
    if batch.product_id != product.id or batch.company_id != company.id:
        raise ValidationError("This batch does not belong to this product/company.")
    return record_stock_movement(
        company=company, product=product, warehouse=warehouse, quantity=Decimal(quantity),
        reason="purchase", reference=reference, batch=batch,
    )


def available_batch_quantity(*, company, product, warehouse, batch):
    """The 'batch stock reconciles by warehouse' figure — always derived
    live from the ledger, never cached."""
    from django.db.models import Sum
    return StockMovement.objects.filter(
        company=company, product=product, warehouse=warehouse, batch=batch,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def suggest_fefo_batches(*, company, product, warehouse, quantity_needed=None):
    """
    First-Expired-First-Out ordering of batches with available stock in
    this warehouse — a **suggestion only** (Phase 31 rule: "FEFO
    suggestion for expiring batch selection as a suggestion only unless
    the business explicitly confirms the batch"). Never selects or
    reserves anything; the caller still has to pass an explicit `batch`
    to validate_batch_availability()/sell_batch_stock() themselves.
    """
    batches = ProductBatch.objects.for_company(company).filter(
        product=product
    ).order_by("expiry_date", "id")

    suggestions = []
    remaining = Decimal(quantity_needed) if quantity_needed is not None else None
    for batch in batches:
        qty = available_batch_quantity(company=company, product=product, warehouse=warehouse, batch=batch)
        if qty <= 0:
            continue
        suggestions.append({"batch": batch, "available_quantity": qty})
        if remaining is not None:
            remaining -= qty
            if remaining <= 0:
                break
    return suggestions


def validate_batch_availability(*, company, product, warehouse, batch, quantity, as_of=None):
    """
    Raises ValidationError when the batch doesn't have enough stock in
    this warehouse, or (when the product forbids it) the batch has
    expired. Called both from sales before selling and from anything
    else that wants to check before committing to a batch.
    """
    if batch.product_id != product.id:
        raise ValidationError("This batch does not belong to this product.")

    as_of = _to_date(as_of) or timezone.localdate()
    if product.block_expired_batch_sale and batch.expiry_date and batch.expiry_date < as_of:
        raise ValidationError(f"Batch {batch.batch_number} expired on {batch.expiry_date} and cannot be sold.")

    available = available_batch_quantity(company=company, product=product, warehouse=warehouse, batch=batch)
    if available < Decimal(quantity):
        raise ValidationError(
            f"Insufficient stock in batch {batch.batch_number} at this warehouse: "
            f"{available} available, {quantity} requested."
        )


def sell_batch_stock(*, company, product, warehouse, batch, quantity, reference=""):
    """Validates then posts the outgoing movement — the single call site
    sales.services.create_invoice() uses for a batch-tracked line."""
    validate_batch_availability(company=company, product=product, warehouse=warehouse, batch=batch, quantity=quantity)
    return record_stock_movement(
        company=company, product=product, warehouse=warehouse, quantity=-Decimal(quantity),
        reason="sale", reference=reference, batch=batch,
    )


# ---------------------------------------------------------------- serials


def register_serial(*, company, product, warehouse, serial_number, received_date=None):
    if product.company_id != company.id:
        raise ValidationError("This product does not belong to the active company.")
    if product.tracking_type != "serial":
        raise ValidationError("This product is not serial-tracked (tracking_type must be 'serial').")
    if ProductSerial.objects.for_company(company).filter(product=product, serial_number=serial_number).exists():
        raise ValidationError(f"Serial number {serial_number} is already registered for this product.")

    serial = ProductSerial.objects.create(
        company=company, product=product, warehouse=warehouse, serial_number=serial_number,
        status="in_stock", received_date=received_date,
    )
    record_stock_movement(
        company=company, product=product, warehouse=warehouse, quantity=Decimal("1"),
        reason="purchase", reference=f"Serial {serial_number}", serial=serial,
    )
    return serial


def validate_serial_availability(*, company, product, serial):
    if serial.product_id != product.id or serial.company_id != company.id:
        raise ValidationError("This serial does not belong to this product/company.")
    if serial.status != "in_stock":
        raise ValidationError(
            f"Serial {serial.serial_number} is not available for sale (status: {serial.get_status_display()})."
        )


@transaction.atomic
def sell_serial_stock(*, company, product, serial, reference=""):
    """Enforces 'serial number cannot be sold twice': re-checks status
    inside the same transaction as the flip, then posts the -1 movement."""
    validate_serial_availability(company=company, product=product, serial=serial)
    serial.status = "sold"
    serial.save(update_fields=["status"])
    return record_stock_movement(
        company=company, product=product, warehouse=serial.warehouse, quantity=Decimal("-1"),
        reason="sale", reference=reference, serial=serial,
    )


def restore_serial_stock(*, company, product, serial, warehouse, reference=""):
    """Used by process_return() — puts a returned serial back in stock."""
    if serial.product_id != product.id or serial.company_id != company.id:
        raise ValidationError("This serial does not belong to this product/company.")
    serial.status = "returned"
    serial.warehouse = warehouse
    serial.save(update_fields=["status", "warehouse"])
    return record_stock_movement(
        company=company, product=product, warehouse=warehouse, quantity=Decimal("1"),
        reason="return", reference=reference, serial=serial,
    )


# ---------------------------------------------------------------- transfers & adjustments


@transaction.atomic
def create_stock_transfer(*, company, user, product, from_warehouse, to_warehouse, quantity, batch=None, reference=""):
    """One transfer = two StockMovement rows (transfer_out at the source,
    transfer_in at the destination) so the aggregate ledger stays
    balanced across warehouses — total company-wide stock for the
    product is unchanged by a transfer, only its location moves."""
    if product.company_id != company.id or from_warehouse.company_id != company.id or to_warehouse.company_id != company.id:
        raise ValidationError("Product and warehouses must all belong to the active company.")
    if from_warehouse.id == to_warehouse.id:
        raise ValidationError("Cannot transfer a warehouse to itself.")
    quantity = Decimal(quantity)

    if batch is not None:
        validate_batch_availability(company=company, product=product, warehouse=from_warehouse, batch=batch, quantity=quantity)
    else:
        available = product.current_stock(warehouse=from_warehouse)
        if Decimal(available) < quantity:
            raise ValidationError(f"Insufficient stock at {from_warehouse.name}: {available} available, {quantity} requested.")

    out_move = record_stock_movement(
        company=company, product=product, warehouse=from_warehouse, quantity=-quantity,
        reason="transfer_out", reference=reference, batch=batch,
    )
    in_move = record_stock_movement(
        company=company, product=product, warehouse=to_warehouse, quantity=quantity,
        reason="transfer_in", reference=reference, batch=batch,
    )
    return out_move, in_move


@transaction.atomic
def create_stock_adjustment(*, company, user, product, warehouse, quantity_delta, reason_note="", batch=None):
    """A direct manual correction outside of sales/purchases/transfers/
    counts — e.g. damage, theft, or a data-entry fix. Always audited,
    same as stock-count completion below."""
    if product.company_id != company.id or warehouse.company_id != company.id:
        raise ValidationError("Product and warehouse must belong to the active company.")
    quantity_delta = Decimal(quantity_delta)
    if quantity_delta == 0:
        raise ValidationError("Adjustment quantity cannot be zero.")

    movement = record_stock_movement(
        company=company, product=product, warehouse=warehouse, quantity=quantity_delta,
        reason="adjustment", reference=reason_note, batch=batch,
    )

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="stock_adjustment", model_name="StockMovement",
        object_id=movement.id, changes={"product_id": product.id, "quantity_delta": str(quantity_delta), "note": reason_note},
    )
    return movement


# ---------------------------------------------------------------- physical stock counts


@transaction.atomic
def start_stock_count(*, company, user, warehouse, products):
    """Snapshots each product's current system quantity in this warehouse
    at the moment counting begins — the count is against *this* snapshot,
    not a live-changing figure, so results are meaningful even if sales
    keep happening elsewhere while counting is in progress."""
    if warehouse.company_id != company.id:
        raise ValidationError("This warehouse does not belong to the active company.")
    for p in products:
        if p.company_id != company.id:
            raise ValidationError("All products must belong to the active company.")

    stock_count = StockCount.objects.create(
        company=company, warehouse=warehouse, date=timezone.localdate(), created_by=user,
    )
    StockCountLine.objects.bulk_create([
        StockCountLine(stock_count=stock_count, product=p, system_quantity=p.current_stock(warehouse=warehouse))
        for p in products
    ])
    return stock_count


def submit_stock_count_line(*, company, stock_count_line, counted_quantity, notes=""):
    if stock_count_line.stock_count.company_id != company.id:
        raise ValidationError("This stock count does not belong to the active company.")
    if stock_count_line.stock_count.status != "draft":
        raise ValidationError("This stock count has already been completed.")

    stock_count_line.counted_quantity = Decimal(counted_quantity)
    stock_count_line.notes = notes
    stock_count_line.save(update_fields=["counted_quantity", "notes"])
    return stock_count_line


@transaction.atomic
def complete_stock_count(*, company, user, stock_count):
    """
    Posts one reconciling StockMovement per line whose counted quantity
    differs from the system snapshot, then writes a single AuditLog entry
    summarizing every variance (Phase 31 acceptance criteria:
    "stock-count adjustment leaves an audit trail"). Rejects completing
    an already-completed count outright rather than double-posting.
    """
    if stock_count.company_id != company.id:
        raise ValidationError("This stock count does not belong to the active company.")
    if stock_count.status == "completed":
        raise ValidationError("This stock count has already been completed.")

    variances = []
    for line in stock_count.lines.select_related("product").all():
        if line.counted_quantity is None:
            continue
        variance = line.counted_quantity - line.system_quantity
        if variance == 0:
            continue
        record_stock_movement(
            company=company, product=line.product, warehouse=stock_count.warehouse,
            quantity=variance, reason="stock_count", reference=f"StockCount#{stock_count.id}",
        )
        variances.append({"product_id": line.product.id, "product_name": line.product.name, "variance": str(variance)})

    stock_count.status = "completed"
    stock_count.completed_by = user
    stock_count.completed_at = timezone.now()
    stock_count.save(update_fields=["status", "completed_by", "completed_at"])

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="complete_stock_count", model_name="StockCount",
        object_id=stock_count.id, changes={"variances": variances},
    )
    return stock_count


# ---------------------------------------------------------------- expiry alerts


def check_batch_expiry_and_notify(company, near_expiry_days=None):
    """
    Dedup via BatchAlertLog — each batch notifies at most once for
    'near_expiry' and once for 'expired', ever (not once per day), same
    fix as Phase 30's overdue-invoice spam applied here up front.
    """
    from datetime import timedelta
    from apps.notifications.services import notify_batch_near_expiry, notify_batch_expired

    from apps.notifications.rules import once, threshold_for, thresholds
    days_rules = [near_expiry_days] if near_expiry_days is not None else (thresholds(company, "product_expiry") or [30])
    today = timezone.localdate()
    horizon = today + timedelta(days=max(days_rules))
    created = []
    warehouses = list(Warehouse.objects.for_company(company))

    batches = ProductBatch.objects.for_company(company).filter(expiry_date__isnull=False)
    for batch in batches:
        has_stock = any(
            available_batch_quantity(company=company, product=batch.product, warehouse=w, batch=batch) > 0
            for w in warehouses
        )
        if not has_stock:
            continue

        if batch.expiry_date < today:
            alert_type = "expired"
        elif batch.expiry_date <= horizon:
            alert_type = "near_expiry"
        else:
            continue

        _, is_new = BatchAlertLog.objects.get_or_create(company=company, batch=batch, alert_type=alert_type)
        if alert_type == "expired":
            if is_new:
                created.append(notify_batch_expired(company, batch))
            continue
        # near expiry: once per configured threshold (e.g. 30, 7 and 1 days before)
        days_left = (batch.expiry_date - today).days
        step = threshold_for(days_left, days_rules)
        if step is not None and once(company, f"batch:{batch.id}:near:{step}"):
            created.append(notify_batch_near_expiry(company, batch, days_left))
    return created
