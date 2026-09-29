from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "company", "user", "action", "model_name", "object_id")
    list_filter = ("action", "model_name")

    def has_delete_permission(self, request, obj=None):
        return False  # append-only, even from the admin (Phase 0 Section 14)

    def has_change_permission(self, request, obj=None):
        return False
