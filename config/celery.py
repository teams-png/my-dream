import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("bookpilot")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat schedule: subscription expiry checks (Phase 0 Section 7 / Phase 1 Section 4),
# plus the two batch-expiry sweeps flagged as TODOs in medical_shop/services.py
# and protein_shop/services.py (Phase 16/17) — closed here in Phase 20.
app.conf.beat_schedule = {
    "check-subscription-expiry-daily": {
        "task": "apps.subscriptions.tasks.check_subscription_expiry",
        "schedule": 60 * 60 * 24,  # once a day; move to crontab(hour=1, minute=0) once deployed
    },
    "check-medicine-batch-expiry-daily": {
        "task": "apps.verticals.medical_shop.tasks.check_medicine_batch_expiry",
        "schedule": 60 * 60 * 24,
    },
    "check-protein-batch-expiry-daily": {
        "task": "apps.verticals.protein_shop.tasks.check_protein_batch_expiry",
        "schedule": 60 * 60 * 24,
    },
    "check-stock-batches-and-overdue-documents-daily": {
        "task": "apps.notifications.tasks.check_low_stock_and_overdue_invoices",
        "schedule": 60 * 60 * 24,
    },
}
