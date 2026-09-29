from django.db import models
from apps.tenants.models import TenantScopedModel


class NotificationType(models.TextChoices):
    SUBSCRIPTION_EXPIRING = "subscription_expiring", "Subscription Expiring Soon"
    SUBSCRIPTION_EXPIRED = "subscription_expired", "Subscription Expired"
    PAYMENT_DUE = "payment_due", "Payment Due"
    LOW_STOCK = "low_stock", "Low Stock"
    PRODUCT_EXPIRY = "product_expiry", "Product Expiry"
    MEMBERSHIP_EXPIRY = "membership_expiry", "Membership Expiry"
    INVOICE_OVERDUE = "invoice_overdue", "Invoice Overdue"
    SUPPLIER_PAYMENT_DUE = "supplier_payment_due", "Supplier Payment Due"
    CUSTOMER_PAYMENT_DUE = "customer_payment_due", "Customer Payment Due"
    GENERAL = "general", "General"


class Notification(TenantScopedModel):
    """
    The in-app feed. `recipient = null` means a company-wide broadcast
    (e.g. "subscription expiring" goes to every Owner-role member, not one
    user) — resolved to individual rows at creation time in services.py
    rather than left ambiguous at read time.
    """
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications",
        null=True, blank=True,
    )
    notif_type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.GENERAL)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    reference_type = models.CharField(max_length=50, blank=True)  # e.g. "sales.SalesInvoice"
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    emailed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]


class NotificationRule(TenantScopedModel):
    """
    Lets an Owner tune *when* they get warned, per type — e.g. "notify me
    at 15/7/1 days" instead of the hardcoded platform default. Absence of a
    rule for a (company, notif_type) pair means: use DEFAULT_THRESHOLDS in
    services.py.
    """
    notif_type = models.CharField(max_length=30, choices=NotificationType.choices)
    days_before = models.PositiveIntegerField(
        help_text="For expiry-style notifications: how many days before the event to fire.",
    )
    also_email = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "notif_type", "days_before")


class NotificationTemplate(TenantScopedModel):
    CHANNELS = [("email", "Email"), ("sms", "SMS"), ("whatsapp", "WhatsApp")]
    event_type = models.CharField(max_length=50)
    channel = models.CharField(max_length=20, choices=CHANNELS, default="email")
    subject_template = models.CharField(max_length=255)
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "event_type", "channel")


class NotificationPreference(TenantScopedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=50)
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    whatsapp_enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = ("company", "user", "event_type")


class NotificationDelivery(TenantScopedModel):
    STATUS = [("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")]
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=20)
    recipient_address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS, default="queued")
    retry_count = models.PositiveSmallIntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "idempotency_key")
        indexes = [models.Index(fields=("company", "status", "created_at"))]
