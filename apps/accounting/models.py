from django.db import models
from apps.tenants.models import TenantScopedModel


class Account(TenantScopedModel):
    TYPE = [
        ("asset", "Asset"), ("liability", "Liability"), ("equity", "Equity"),
        ("income", "Income"), ("expense", "Expense"),
    ]
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=TYPE)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_system_account = models.BooleanField(default=False)  # seeded ones — cannot be deleted
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "code")

    def __str__(self):
        return f"{self.code} {self.name}"


class FiscalYear(TenantScopedModel):
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    lock_date = models.DateField(
        null=True, blank=True,
        help_text=(
            "Ordinary users cannot post journal entries dated on or before "
            "this date. A user whose role has accounting.override_period_lock "
            "can still post here. Independent of is_closed."
        ),
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT,
        related_name="closed_fiscal_years",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        state = "closed" if self.is_closed else "open"
        return f"FY {self.start_date} to {self.end_date} ({state})"


class JournalEntry(TenantScopedModel):
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    memo = models.TextField(blank=True)
    source_type = models.CharField(max_length=50, blank=True)   # "sales_invoice", "purchase", "expense", "manual"
    source_id = models.PositiveIntegerField(null=True, blank=True)
    posted_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    is_void = models.BooleanField(default=False)  # reversing entries, never hard-delete a posted entry

    def __str__(self):
        return f"JE#{self.id} {self.date} {self.reference}"

    class Meta:
        indexes = [models.Index(fields=("company", "date", "is_void")), models.Index(fields=("company", "source_type", "source_id"))]


class JournalLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)
