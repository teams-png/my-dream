from django.db import models
from apps.tenants.models import TenantScopedModel


class Customer(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="0 means no limit. Checked via apps.collections.services.customer_credit_status().",
    )
    payment_terms_days = models.PositiveIntegerField(
        default=30, help_text="Default due-date offset for new invoices to this customer.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class LoyaltyAccount(TenantScopedModel):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="loyalty_account")
    points_balance = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.customer.name} — {self.points_balance} pts"


class LoyaltyTransaction(TenantScopedModel):
    TYPE = [("earn", "Earned"), ("redeem", "Redeemed"), ("adjust", "Adjustment")]
    account = models.ForeignKey(LoyaltyAccount, on_delete=models.CASCADE, related_name="transactions")
    points = models.IntegerField()
    type = models.CharField(max_length=20, choices=TYPE)
    reference = models.CharField(max_length=100, blank=True)
    date = models.DateField()
