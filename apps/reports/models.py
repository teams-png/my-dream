from django.db import models
from apps.tenants.models import TenantScopedModel


class ReportExport(TenantScopedModel):
    """
    Audit trail row created every time a report is downloaded as CSV
    (see apps.reports.views._maybe_export). Every other report here is
    computed on the fly from other apps' data — this is the one thing
    actually persisted by this app.
    """
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    report_code = models.CharField(max_length=50)
    format = models.CharField(max_length=10, default="csv")
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
