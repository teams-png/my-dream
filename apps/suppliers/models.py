from django.db import models
from apps.tenants.models import TenantScopedModel


class Supplier(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_terms_days = models.PositiveIntegerField(
        default=30, help_text="Default due-date offset for new bills from this supplier.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
