from django.db import models
from apps.tenants.models import TenantScopedModel


class MedicineBatch(TenantScopedModel):
    """
    Unlike MobileUnit/CycleUnit (one row per physical, individually-serialed
    item), a medicine batch is fungible: one row per (product, batch_number)
    holding a quantity, not a single item with a status. Stock for a batch
    is tracked here directly (quantity_remaining) rather than through
    inventory.StockMovement, because dispensing needs batch-level FEFO
    (first-expiry-first-out) accuracy that a company-wide movement ledger
    doesn't give per batch.
    """
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="medicine_batches")
    batch_number = models.CharField(max_length=50)
    manufacturer = models.CharField(max_length=150, blank=True)
    expiry_date = models.DateField()
    received_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_remaining = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("company", "product", "batch_number")

    def __str__(self):
        return f"{self.product.name} - batch {self.batch_number} (exp {self.expiry_date})"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expiry_date < timezone.localdate()


class DispenseRecord(TenantScopedModel):
    """
    One sale/dispense event out of a specific batch. Kept separate from
    sales.SalesInvoice (same TODO as every other vertical — see services.py)
    so this vertical can go live without waiting for that integration, while
    still capturing the prescription reference Phase 1 Section 12 asks for.
    """
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT, related_name="dispense_records")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="medicine_dispenses",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    sold_price = models.DecimalField(max_digits=10, decimal_places=2)
    sold_date = models.DateField()
    prescription_reference = models.CharField(
        max_length=100, blank=True,
        help_text="Doctor / prescription ID, where legally required for this medicine.",
    )
    is_returned = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.batch.product.name} x{self.quantity} ({self.sold_date})"
