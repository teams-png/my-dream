"""
Phase 26: closes the invoice-linkage TODO. dispense() now invoices via
sales.services.create_invoice() before decrementing batch stock, so every
dispense shows up in accounting/reports — DispenseRecord + MedicineBatch
remain the source of truth for FEFO/batch-level quantity (a company-wide
StockMovement ledger can't give that same batch accuracy), so the Product
behind a medical_shop batch should be created with is_stock_tracked=False
(same convention as gym/spa's linked Products) to avoid
reports.stock_report double-counting against quantity_remaining.
"""
from django.db import transaction

from apps.customers.services import get_or_create_walkin_customer
from apps.notifications.services import notify_product_expiry
from apps.sales.services import create_invoice

from .models import MedicineBatch, DispenseRecord


@transaction.atomic
def dispense(batch, *, company, user, warehouse, quantity, sold_price, sold_date, customer=None, prescription_reference=""):
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    if quantity > batch.quantity_remaining:
        raise ValueError(
            f"Only {batch.quantity_remaining} remaining in batch {batch.batch_number}, cannot dispense {quantity}."
        )
    if batch.is_expired:
        raise ValueError(f"Batch {batch.batch_number} expired on {batch.expiry_date}, cannot dispense.")

    invoice_customer = customer or get_or_create_walkin_customer(company)
    create_invoice(
        company=company, user=user, customer=invoice_customer, date=sold_date, warehouse=warehouse,
        lines=[{"product": batch.product, "quantity": quantity, "unit_price": sold_price}],
    )

    batch.quantity_remaining -= quantity
    batch.save(update_fields=["quantity_remaining"])

    return DispenseRecord.objects.create(
        company=batch.company, batch=batch, customer=customer, quantity=quantity,
        sold_price=sold_price, sold_date=sold_date, prescription_reference=prescription_reference,
    )


@transaction.atomic
def return_dispense(record):
    if record.is_returned:
        raise ValueError("This dispense record was already returned.")
    record.is_returned = True
    record.save(update_fields=["is_returned"])

    batch = record.batch
    batch.quantity_remaining += record.quantity
    batch.save(update_fields=["quantity_remaining"])
    return record


def check_expiring_batches(company, thresholds=(90, 30, 7)):
    """
    Sweep for batches nearing expiry (Phase 1 Section 23: "Product expiry"
    notification) that still have stock left. Intended to be called once a
    day per company — wire into the same Celery beat schedule as
    apps.subscriptions.services.run_daily_expiry_check (Phase 16/18), not
    called from request/view code.
    """
    from datetime import timedelta
    from django.utils import timezone

    today = timezone.localdate()
    notified = []
    batches = MedicineBatch.objects.for_company(company).filter(quantity_remaining__gt=0)
    for batch in batches:
        days_left = (batch.expiry_date - today).days
        if days_left in thresholds:
            notify_product_expiry(batch, days_left)
            notified.append(batch)
    return notified
