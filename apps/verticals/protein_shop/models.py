from django.db import models
from apps.tenants.models import TenantScopedModel


class ProteinBatch(TenantScopedModel):
    """
    Same reasoning as medical_shop.MedicineBatch: a protein-powder tub is
    fungible within a batch, so this is batch-level quantity, not a
    per-unit row. `flavour` and `weight_grams` live here rather than on a
    new "ProteinProduct" wrapper around inventory.Product — the base
    Product (Section 11) already covers name/brand/category/pricing, and a
    given SKU's flavour/pack size is effectively fixed per batch of stock
    received, so adding a whole parallel product model would just
    duplicate what Product already does (Phase 1 Section 12 warns against
    this).
    """
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="protein_batches")
    batch_number = models.CharField(max_length=50)
    flavour = models.CharField(max_length=100, blank=True)
    weight_grams = models.PositiveIntegerField(help_text="Pack size, e.g. 1000 for a 1kg tub.")
    expiry_date = models.DateField()
    received_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_remaining = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("company", "product", "batch_number")

    def __str__(self):
        return f"{self.product.name} ({self.flavour or 'unflavoured'}, {self.weight_grams}g) - batch {self.batch_number}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expiry_date < timezone.localdate()


class SaleRecord(TenantScopedModel):
    """
    One sale event out of a specific batch. Same TODO as medical_shop's
    DispenseRecord — not yet routed through sales.services.create_invoice().
    """
    batch = models.ForeignKey(ProteinBatch, on_delete=models.PROTECT, related_name="sale_records")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="protein_sales",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    sold_price = models.DecimalField(max_digits=10, decimal_places=2)
    sold_date = models.DateField()
    is_returned = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.batch.product.name} x{self.quantity} ({self.sold_date})"
