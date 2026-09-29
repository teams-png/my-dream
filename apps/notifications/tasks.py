from celery import shared_task
from apps.tenants.models import Company

from .services import check_low_stock_and_notify, check_overdue_invoices_and_notify


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def deliver_notification(self, delivery_id):
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone
    from .models import NotificationDelivery, NotificationTemplate

    delivery = NotificationDelivery.objects.select_related("notification").filter(pk=delivery_id).first()
    if not delivery or delivery.status == "sent":
        return
    notification = delivery.notification
    template = NotificationTemplate.objects.filter(
        company=delivery.company, event_type=notification.notif_type, channel=delivery.channel, is_active=True,
    ).first()
    subject = template.subject_template.format(title=notification.title) if template else notification.title
    body = template.body_template.format(title=notification.title, message=notification.message) if template else notification.message
    try:
        if delivery.channel != "email":
            delivery.status = "skipped"
            delivery.failure_reason = "No provider adapter configured for this channel."
        else:
            send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"), [delivery.recipient_address])
            delivery.status = "sent"
            delivery.sent_at = timezone.now()
            notification.emailed = True
            notification.save(update_fields=["emailed"])
            delivery.failure_reason = ""
        delivery.save(update_fields=["status", "failure_reason", "sent_at"])
    except Exception as exc:
        delivery.retry_count += 1
        delivery.status = "failed"
        delivery.failure_reason = str(exc)[:1000]
        delivery.save(update_fields=["retry_count", "status", "failure_reason"])
        raise


@shared_task
def check_low_stock_and_overdue_invoices():
    """Runs daily alongside subscriptions.tasks.check_subscription_expiry (config/celery.py beat schedule)."""
    for company in Company.objects.filter(is_active=True):
        check_low_stock_and_notify(company)
        check_overdue_invoices_and_notify(company)
        from apps.inventory.services import check_batch_expiry_and_notify
        check_batch_expiry_and_notify(company)
