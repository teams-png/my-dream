from django.contrib import admin
from .models import Notification, NotificationRule


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "recipient", "notif_type", "is_read", "emailed", "created_at")
    list_filter = ("notif_type", "is_read", "emailed")
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False  # created only via notifications.services


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ("company", "notif_type", "days_before", "also_email")
    list_filter = ("notif_type",)
