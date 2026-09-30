from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

    def ready(self):
        # registers the per-company daily jobs (owner's daily report)
        from . import daily_report  # noqa: F401
