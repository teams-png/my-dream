from django.db import models
from apps.tenants.models import TenantScopedModel


class ExpenseCategory(TenantScopedModel):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Expense(TenantScopedModel):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=30, default="cash")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)


class ExpenseBudget(TenantScopedModel):
    """A monthly spending limit for one expense category, with an early-warning percentage."""
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name="budgets")
    monthly_amount = models.DecimalField(max_digits=14, decimal_places=2)
    alert_percent = models.PositiveSmallIntegerField(default=80)

    class Meta:
        unique_together = ("company", "category")
