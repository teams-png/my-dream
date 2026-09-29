"""
Finance tools shared by every business type:
post-dated cheques (PDC), recurring invoices and fixed assets.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.tenants.models import TenantScopedModel


class PostDatedCheque(TenantScopedModel):
    DIRECTION = [("received", _("Received from customer")), ("issued", _("Issued to supplier"))]
    STATUS = [
        ("pending", _("Pending")), ("deposited", _("Deposited")), ("cleared", _("Cleared")),
        ("bounced", _("Bounced")), ("cancelled", _("Cancelled")),
    ]
    direction = models.CharField(max_length=10, choices=DIRECTION)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="pdcs")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="pdcs")
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="pdcs")
    purchase = models.ForeignKey("purchases.Purchase", null=True, blank=True, on_delete=models.SET_NULL, related_name="pdcs")
    cheque_number = models.CharField(max_length=40)
    bank_name = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    cheque_date = models.DateField(help_text="Date written on the cheque (when it can be cashed).")
    received_on = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    deposited_on = models.DateField(null=True, blank=True)
    cleared_on = models.DateField(null=True, blank=True)
    bounce_reason = models.CharField(max_length=255, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    reminder_sent_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["cheque_date", "id"]

    @property
    def party(self):
        return self.customer or self.supplier

    def __str__(self):
        return f"Cheque {self.cheque_number} · {self.amount}"


class RecurringInvoice(TenantScopedModel):
    FREQUENCY = [("weekly", _("Weekly")), ("monthly", _("Monthly")), ("quarterly", _("Every 3 months")), ("yearly", _("Yearly"))]
    name = models.CharField(max_length=120, help_text="e.g. Monthly maintenance contract")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="recurring_invoices")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    frequency = models.CharField(max_length=10, choices=FREQUENCY, default="monthly")
    next_run_date = models.DateField()
    anchor_day = models.PositiveSmallIntegerField(default=0, help_text="Day of month to bill on (keeps 31st billing at month end).")
    end_date = models.DateField(null=True, blank=True)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    email_customer = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    invoices_created = models.PositiveIntegerField(default=0)
    last_invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_run_date", "id"]

    @property
    def amount(self):
        subtotal = sum((line.quantity * line.unit_price for line in self.lines.all()), Decimal("0"))
        return subtotal + (subtotal * self.tax_percent / Decimal("100")).quantize(Decimal("0.01"))

    def __str__(self):
        return self.name


class RecurringInvoiceLine(models.Model):
    recurring = models.ForeignKey(RecurringInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)


class FixedAsset(TenantScopedModel):
    STATUS = [("active", _("In use")), ("disposed", _("Disposed"))]
    PAID_FROM = [("bank", _("Bank")), ("cash", _("Cash")), ("payable", _("On credit (supplier)")), ("none", _("Already owned (no payment now)"))]
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=80, blank=True, help_text="e.g. Kitchen equipment, Vehicles, Furniture")
    asset_code = models.CharField(max_length=40, blank=True)
    purchase_date = models.DateField()
    cost = models.DecimalField(max_digits=14, decimal_places=2)
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    useful_life_months = models.PositiveIntegerField(default=60)
    paid_from = models.CharField(max_length=10, choices=PAID_FROM, default="bank")
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    disposed_on = models.DateField(null=True, blank=True)
    disposal_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    purchase_entry = models.ForeignKey("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchase_date", "id"]

    @property
    def monthly_depreciation(self):
        if not self.useful_life_months:
            return Decimal("0")
        return ((self.cost - self.salvage_value) / self.useful_life_months).quantize(Decimal("0.01"))

    @property
    def accumulated_depreciation(self):
        return sum((d.amount for d in self.depreciation_entries.all()), Decimal("0"))

    @property
    def book_value(self):
        return self.cost - self.accumulated_depreciation

    def __str__(self):
        return self.name


class DepreciationEntry(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="depreciation_entries")
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    journal_entry = models.ForeignKey("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = ("asset", "period_end")
        ordering = ["period_end"]
