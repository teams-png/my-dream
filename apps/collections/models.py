from django.db import models
from apps.tenants.models import TenantScopedModel


class AgeingBucket(TenantScopedModel):
    """
    Configurable per company (Phase 30 rule: "ageing buckets should be
    configurable but seed standard 0-30, 31-60, 61-90, 90+ day views").
    `max_days=None` means open-ended (the "90+" bucket). Buckets are for
    days *past due* only — an invoice/bill that isn't due yet never falls
    into any bucket (acceptance criteria: "future-due invoices are not
    shown as overdue"); that's tracked separately as "not yet due".
    """
    label = models.CharField(max_length=30)
    min_days = models.PositiveIntegerField()
    max_days = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        unique_together = ("company", "label")

    def __str__(self):
        return self.label

    def matches(self, days_overdue):
        if days_overdue < self.min_days:
            return False
        if self.max_days is not None and days_overdue > self.max_days:
            return False
        return True


DEFAULT_AGEING_BUCKETS = [
    # (label, min_days, max_days, order)
    ("0-30", 0, 30, 1),
    ("31-60", 31, 60, 2),
    ("61-90", 61, 90, 3),
    ("90+", 91, None, 4),
]


class CollectionNote(TenantScopedModel):
    """
    A follow-up note against either a customer (AR) or a supplier (AP),
    optionally tied to a specific invoice/bill. Exactly one of
    (customer, supplier) must be set — enforced in services.py, not here,
    to keep the model itself simple (Phase 0 Section 1: business rules
    live in services).
    """
    PARTY_TYPE = [("customer", "Customer"), ("supplier", "Supplier")]

    party_type = models.CharField(max_length=10, choices=PARTY_TYPE)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="collection_notes")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.CASCADE, related_name="collection_notes")
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="collection_notes")
    purchase = models.ForeignKey("purchases.Purchase", null=True, blank=True, on_delete=models.SET_NULL, related_name="collection_notes")
    note = models.TextField()
    follow_up_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OverdueNotification(TenantScopedModel):
    """
    Dedup marker: one row per (document, ageing bucket) that's already
    been notified on. This is what makes the daily overdue check
    idempotent (Phase 30 rule: "without creating duplicates every day") —
    an invoice sitting in the same bucket for a week only ever notifies
    once; a new row (and a new notification) only gets created when it
    *escalates* into the next bucket.
    """
    SOURCE_TYPE = [("sales_invoice", "Sales Invoice"), ("purchase", "Purchase")]

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE)
    source_id = models.PositiveIntegerField()
    bucket_label = models.CharField(max_length=30)
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "source_type", "source_id", "bucket_label")
