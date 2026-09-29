from django.db import models


class PaymentGatewaySettings(models.Model):
    """Singleton platform payment configuration; secret values are encrypted at rest."""

    stripe_enabled = models.BooleanField(default=False)
    stripe_test_mode = models.BooleanField(default=True)
    stripe_publishable_key_ciphertext = models.TextField(blank=True)
    stripe_secret_key_ciphertext = models.TextField(blank=True)
    stripe_webhook_secret_ciphertext = models.TextField(blank=True)

    razorpay_enabled = models.BooleanField(default=False)
    razorpay_test_mode = models.BooleanField(default=True)
    razorpay_key_id_ciphertext = models.TextField(blank=True)
    razorpay_key_secret_ciphertext = models.TextField(blank=True)
    razorpay_webhook_secret_ciphertext = models.TextField(blank=True)

    # SkipCash — Qatar (cards, Apple Pay, Google Pay, local debit)
    skipcash_enabled = models.BooleanField(default=False)
    skipcash_test_mode = models.BooleanField(default=True)
    skipcash_client_id_ciphertext = models.TextField(blank=True)
    skipcash_key_id_ciphertext = models.TextField(blank=True)
    skipcash_key_secret_ciphertext = models.TextField(blank=True)
    skipcash_webhook_key_ciphertext = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name_plural = "Payment gateway settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def set_secret(self, field_name, value):
        from .payment_gateways import encrypt_credential
        setattr(self, f"{field_name}_ciphertext", encrypt_credential(value) if value else "")

    def get_secret(self, field_name):
        from .payment_gateways import decrypt_credential
        value = getattr(self, f"{field_name}_ciphertext", "")
        return decrypt_credential(value) if value else ""


class SupportTicket(models.Model):
    """
    Deliberately NOT a TenantScopedModel — a platform admin must see every
    tenant's tickets in one queue, and a ticket can outlive the membership
    of the user who raised it.
    """
    STATUS = [("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")]
    PRIORITY = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]

    company = models.ForeignKey("tenants.Company", on_delete=models.CASCADE, related_name="support_tickets")
    raised_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="+")
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="open")
    priority = models.CharField(max_length=20, choices=PRIORITY, default="normal")
    assigned_to = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        limit_choices_to={"is_platform_admin": True},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.subject} ({self.company.name})"
