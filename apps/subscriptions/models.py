from django.db import models


class SubscriptionPlan(models.Model):
    BILLING_PERIOD = [("monthly", "Monthly"), ("yearly", "Yearly")]

    name = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Global", help_text="Which country/region this price applies to")
    currency = models.CharField(max_length=3, default="QAR")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_period = models.CharField(max_length=20, choices=BILLING_PERIOD, default="yearly")
    TIERS = [("standard", "Normal business"), ("large", "Supermarket / large shop")]
    tier = models.CharField(
        max_length=10, choices=TIERS, default="standard",
        help_text="Which businesses this price is for; see apps/subscriptions/pricing.py.",
    )
    max_users = models.PositiveIntegerField(default=5)
    max_warehouses = models.PositiveIntegerField(default=1)
    extra_user_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Price per year for each user above max_users. 0 = no extra users (upgrade the plan instead).")
    extra_branch_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Price per year for each branch above max_warehouses. 0 = branches are free.")
    max_invoices_per_month = models.PositiveIntegerField(default=0, help_text="0 means unlimited")
    storage_limit_mb = models.PositiveIntegerField(default=0, help_text="0 means not enforced")
    grace_period_days = models.PositiveSmallIntegerField(default=0)
    modules = models.ManyToManyField("modules.Module", related_name="plans")
    is_active = models.BooleanField(default=True)  # retire old plans without deleting

    def __str__(self):
        return f"{self.name} ({self.country}) — {self.currency} {self.price}"


class Subscription(models.Model):
    STATUS = [("trial", "Trial"), ("active", "Active"), ("expired", "Expired"), ("cancelled", "Cancelled")]

    company = models.OneToOneField("tenants.Company", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="trial")
    auto_renew = models.BooleanField(default=False)
    trial_ends_at = models.DateField(null=True, blank=True)
    grace_ends_at = models.DateField(null=True, blank=True)
    downgrade_effective_on = models.DateField(null=True, blank=True)

    def days_remaining(self):
        from django.utils import timezone
        return (self.end_date - timezone.localdate()).days


class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=30, default="manual")  # abstraction point for a future gateway
    reference = models.CharField(max_length=100, blank=True)
    submitted_by_client = models.BooleanField(default=False)
    is_confirmed = models.BooleanField(default=True)  # False while a client-submitted payment awaits admin approval
    notes = models.TextField(blank=True)


class SubscriptionRenewal(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="renewals")
    previous_end_date = models.DateField()
    new_end_date = models.DateField()
    renewed_at = models.DateTimeField(auto_now_add=True)

class ClientCommercialProfile(models.Model):
    """Platform-owner commercial controls that sit above the tenant's accounting data."""
    company = models.OneToOneField('tenants.Company', on_delete=models.CASCADE, related_name='commercial_profile')
    max_branches = models.PositiveIntegerField(default=1)
    max_pos_terminals = models.PositiveIntegerField(default=1)
    api_calls_per_month = models.PositiveIntegerField(default=0, help_text='0 means unlimited')
    custom_monthly_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reseller_name = models.CharField(max_length=120, blank=True)
    white_label_name = models.CharField(max_length=120, blank=True)
    custom_domain = models.CharField(max_length=255, blank=True)
    admin_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class UsageSnapshot(models.Model):
    company = models.ForeignKey('tenants.Company', on_delete=models.CASCADE, related_name='usage_snapshots')
    period = models.CharField(max_length=7, help_text='YYYY-MM')
    invoices = models.PositiveIntegerField(default=0)
    api_calls = models.PositiveIntegerField(default=0)
    storage_mb = models.PositiveIntegerField(default=0)
    captured_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('company', 'period')


class GatewayCheckout(models.Model):
    """
    One online payment attempt at a hosted checkout (SkipCash). The
    subscription is only extended after the gateway itself confirms the
    payment, and `status` makes that happen exactly once even when the
    return page and the webhook both arrive.
    """
    STATUS = [("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed / cancelled")]

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="gateway_checkouts")
    gateway = models.CharField(max_length=20, default="skipcash")
    transaction_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=64, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    status_detail = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.gateway} {self.transaction_id} ({self.status})"


class SubscriptionInvoice(models.Model):
    """BookPilot's invoice to a client for one subscription period.

    Issued ahead of a renewal (unpaid) or created when a payment renews the subscription (paid).
    apps.subscriptions.billing keeps invoices, payments and renewals in step."""
    STATUS = [("unpaid", "Unpaid"), ("paid", "Paid"), ("void", "Cancelled")]

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField(max_length=30, blank=True, db_index=True)
    issued_on = models.DateField()
    due_on = models.DateField()
    period_start = models.DateField()
    period_end = models.DateField()
    plan_name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=8, choices=STATUS, default="unpaid")
    payment = models.OneToOneField(SubscriptionPayment, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="invoice")
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self):
        return self.number or f"Invoice {self.pk}"
