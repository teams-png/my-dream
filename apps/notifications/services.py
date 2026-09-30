"""
Central notification creation point (Phase 0 Section 23). In-app only for
this scaffold — email/SMS/WhatsApp are future integrations per the master
prompt (Section 23: "Design SMS/WhatsApp integration as future features").
Every notify_* helper below is the single place each event type is worded,
so other apps call these instead of constructing Notification rows inline.
"""
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from .models import Notification, NotificationPreference, NotificationDelivery


def notify(*, company, title, message="", notif_type="general", recipient=None, idempotency_key=None):
    notification = Notification.objects.create(
        company=company, recipient=recipient, notif_type=notif_type, title=title, message=message,
    )
    from .rules import email_enabled
    if not email_enabled(company, notif_type):
        return notification
    recipients = [recipient] if recipient else [m.user for m in company.memberships.filter(is_active=True).select_related("user")]
    for user in recipients:
        if not user or not user.email:
            continue
        preference = NotificationPreference.objects.filter(company=company, user=user, event_type=notif_type).first()
        if preference and not preference.email_enabled:
            continue
        key = idempotency_key or f"notification:{notification.id}:email:{user.id}"
        delivery, created = NotificationDelivery.objects.get_or_create(
            company=company, idempotency_key=key,
            defaults={"notification": notification, "channel": "email", "recipient_address": user.email},
        )
        if created:
            transaction.on_commit(lambda delivery_id=delivery.id: _queue_delivery(delivery_id))
    return notification


def _queue_delivery(delivery_id):
    from .tasks import deliver_notification
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        deliver_notification(delivery_id)
    else:
        deliver_notification.delay(delivery_id)


def notify_subscription_expiring(company, days_left):
    """Called by apps.subscriptions.services.run_daily_expiry_check at the 30/15/7/3/1-day thresholds."""
    return notify(
        company=company, notif_type="subscription_expiring",
        title=f"Your subscription expires in {days_left} day{'s' if days_left != 1 else ''}",
        message="Renew your plan to avoid losing access to your account.",
    )


def notify_subscription_expired(company):
    return notify(
        company=company, notif_type="subscription_expired",
        title="Your subscription has expired",
        message="Renew now to restore full access.",
    )


def notify_low_stock(company, product):
    return notify(
        company=company, notif_type="low_stock",
        title=f"Low stock: {product.name}",
        message=f"Current stock ({product.current_stock()}) is at or below the reorder level ({product.reorder_level}).",
    )


def notify_invoice_overdue(company, invoice):
    return notify(
        company=company, notif_type="invoice_overdue",
        title=f"Invoice {invoice.invoice_number} is overdue",
        message=f"Outstanding: {invoice.total - invoice.amount_paid} from {invoice.customer.name}.",
    )


def notify_bill_overdue(company, purchase):
    label = purchase.bill_number or f"#{purchase.id}"
    return notify(
        company=company, notif_type="supplier_payment_due",
        title=f"Bill {label} is overdue",
        message=f"Outstanding: {purchase.total - purchase.amount_paid} owed to {purchase.supplier.name}.",
    )


def notify_batch_near_expiry(company, batch, days_left):
    return notify(
        company=company, notif_type="product_expiry",
        title=f"Batch expiring soon: {batch.product.name} · {batch.batch_number}",
        message=f"This batch expires in {days_left} day(s) ({batch.expiry_date}).",
    )


def notify_batch_expired(company, batch):
    return notify(
        company=company, notif_type="product_expiry",
        title=f"Batch expired: {batch.product.name} · {batch.batch_number}",
        message=f"This batch expired on {batch.expiry_date} and still has stock on hand.",
    )


def notify_product_expiry(batch, days_left):
    """
    Generic expiry-alert hook used by any vertical with perishable/dated
    stock (protein_shop batches, medical_shop medicine batches, etc.) —
    Section 23 groups these under one notification type rather than a
    bespoke one per vertical.
    """
    return notify(
        company=batch.company, notif_type="product_expiry",
        title=f"Expiring soon: {batch}",
        message=f"This batch expires in {days_left} day(s).",
    )


def check_low_stock_and_notify(company):
    """
    Called by a Celery beat task alongside the subscription expiry check.
    Deliberately separate from inventory.services so inventory doesn't
    depend on notifications (Phase 0 Section 5's one-way dependency rule
    applies between any two non-core apps too, not just verticals→core).
    """
    from apps.inventory.models import Product

    low = Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
    for product in low:
        if product.current_stock() <= product.reorder_level:
            # Avoid spamming: only notify if we haven't already for this product today.
            already_notified_today = Notification.objects.filter(
                company=company, notif_type="low_stock", title__startswith=f"Low stock: {product.name}",
                created_at__date=timezone.localdate(),
            ).exists()
            if not already_notified_today:
                notify_low_stock(company, product)


def check_overdue_invoices_and_notify(company):
    """
    Phase 30: delegates to apps.collections.services.generate_overdue_notifications,
    which dedupes by (invoice, ageing bucket) instead of "already notified
    today" — a still-overdue invoice sitting in the same bucket no longer
    gets a fresh notification every single day; it only fires again when
    it escalates into the next bucket. Also now covers overdue supplier
    bills (AP), not just customer invoices (AR) — same call, same
    existing Celery beat task / webapp call sites, no changes needed there.
    """
    from apps.collections.services import generate_overdue_notifications
    return generate_overdue_notifications(company)
