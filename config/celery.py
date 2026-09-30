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
    # One entry for everything daily (reminders, overdue, expiry, subscriptions, recurring invoices,
    # daily owner reports, budgets) — see apps/notifications/daily.py. Without a worker the same job
    # runs from `manage.py run_daily_jobs` or the /cron/daily/ URL.
    "run-daily-jobs": {
        "task": "apps.notifications.tasks.run_daily_jobs_task",
        "schedule": 60 * 60 * 24,
    },
}
