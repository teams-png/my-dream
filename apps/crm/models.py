from django.db import models
from apps.tenants.models import TenantScopedModel


class PipelineStage(TenantScopedModel):
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=0)
    probability = models.PositiveSmallIntegerField(default=0)
    is_closed = models.BooleanField(default=False)
    is_won = models.BooleanField(default=False)

    class Meta:
        unique_together = ("company", "name")
        ordering = ("order", "id")


class Lead(TenantScopedModel):
    STATUS = [("open", "Open"), ("qualified", "Qualified"), ("converted", "Converted"), ("lost", "Lost")]
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="open")
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_leads")
    converted_customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_crm_leads")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("company", "status", "assigned_to"))]


class Opportunity(TenantScopedModel):
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=255)
    stage = models.ForeignKey(PipelineStage, on_delete=models.PROTECT)
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_opportunities")
    expected_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_close_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("company", "stage", "expected_close_date"))]


class Activity(TenantScopedModel):
    TYPE = [("call", "Call"), ("email", "Email"), ("meeting", "Meeting"), ("task", "Task"), ("note", "Note")]
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    opportunity = models.ForeignKey(Opportunity, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=20, choices=TYPE)
    subject = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_crm_activities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("company", "assigned_to", "due_at"))]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.lead_id) == bool(self.opportunity_id):
            raise ValidationError("An activity must belong to exactly one lead or opportunity.")
