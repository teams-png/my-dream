"""
Phase 26: closes the invoice-linkage TODO. sell() now invoices via
sales.services.create_invoice() before decrementing batch stock — same
shape and same is_stock_tracked=False recommendation as medical_shop's
dispense() (Phase 26), for the same FEFO/batch-accuracy reason.
"""
from django.db import transaction

from apps.customers.services import get_or_create_walkin_customer
from apps.notifications.services import notify_product_expiry
from apps.sales.services import create_invoice

from .models import ProteinBatch, SaleRecord


@transaction.atomic
def sell(batch, *, company, user, warehouse, quantity, sold_price, sold_date, customer=None):
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    if quantity > batch.quantity_remaining:
        raise ValueError(
            f"Only {batch.quantity_remaining} remaining in batch {batch.batch_number}, cannot sell {quantity}."
        )
    if batch.is_expired:
        raise ValueError(f"Batch {batch.batch_number} expired on {batch.expiry_date}, cannot sell.")

    invoice_customer = customer or get_or_create_walkin_customer(company)
    create_invoice(
        company=company, user=user, customer=invoice_customer, date=sold_date, warehouse=warehouse,
        lines=[{"product": batch.product, "quantity": quantity, "unit_price": sold_price}],
    )

    batch.quantity_remaining -= quantity
    batch.save(update_fields=["quantity_remaining"])

    return SaleRecord.objects.create(
        company=batch.company, batch=batch, customer=customer,
        quantity=quantity, sold_price=sold_price, sold_date=sold_date,
    )


@transaction.atomic
def return_sale(record):
    if record.is_returned:
        raise ValueError("This sale was already returned.")
    record.is_returned = True
    record.save(update_fields=["is_returned"])

    batch = record.batch
    batch.quantity_remaining += record.quantity
    batch.save(update_fields=["quantity_remaining"])
    return record


def check_expiring_batches(company, thresholds=(90, 30, 7)):
    """
    Same sweep as medical_shop.services.check_expiring_batches — intended
    for the shared daily Celery beat schedule (Phase 19), not called from
    request/view code.
    """
    from django.utils import timezone

    today = timezone.localdate()
    notified = []
    batches = ProteinBatch.objects.for_company(company).filter(quantity_remaining__gt=0)
    for batch in batches:
        days_left = (batch.expiry_date - today).days
        if days_left in thresholds:
            notify_product_expiry(batch, days_left)
            notified.append(batch)
    return notified
