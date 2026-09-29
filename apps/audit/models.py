from django.db import models
from apps.tenants.models import TenantScopedModel


class AuditLog(TenantScopedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)          # "create", "update", "delete", "login", ...
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    changes = models.JSONField(blank=True, default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=("company", "timestamp")), models.Index(fields=("company", "model_name", "object_id"))]
