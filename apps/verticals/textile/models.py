from django.db import models
from apps.tenants.models import TenantScopedModel


class FabricDetail(TenantScopedModel):
    """
    One-to-one extension of inventory.Product, not a parallel product table
    (Phase 1 Section 12 — avoids duplicating stock/pricing logic that
    inventory.Product already owns).
    """
    FABRIC_TYPE = [
        ("saree", "Saree"), ("dress_material", "Dress Material"),
        ("shirting", "Shirting"), ("suiting", "Suiting"), ("other", "Other"),
    ]
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.CASCADE, related_name="fabric_detail",
    )
    fabric_type = models.CharField(max_length=20, choices=FABRIC_TYPE, default="other")
    color = models.CharField(max_length=50, blank=True)
    design = models.CharField(max_length=100, blank=True)
    material = models.CharField(max_length=100, blank=True)  # cotton, silk, polyester, ...
    length_per_unit = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Meters per unit sold, if sold by piece rather than by meter.",
    )
    width_inches = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.product.name} ({self.get_fabric_type_display()})"


class Measurement(TenantScopedModel):
    """
    `values` is a JSONField rather than fixed columns (chest/waist/...)
    because required fields differ wildly by garment type (shirt vs
    blouse vs pant vs saree blouse) — fixed columns would mean a null-heavy
    table or a new migration for every garment type added.
    """
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="measurements")
    garment_type = models.CharField(max_length=50)  # "shirt", "pant", "blouse", "kurta", ...
    values = models.JSONField(default=dict, blank=True)  # e.g. {"chest": 40, "waist": 34, "sleeve": 24}
    taken_on = models.DateField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.customer.name} - {self.garment_type} ({self.taken_on})"


class TailoringOrder(TenantScopedModel):
    STATUS = [
        ("pending", "Pending"), ("in_progress", "In Progress"),
        ("ready", "Ready for Pickup"), ("delivered", "Delivered"), ("cancelled", "Cancelled"),
    ]

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="tailoring_orders")
    measurement = models.ForeignKey(Measurement, on_delete=models.SET_NULL, null=True, blank=True)
    fabric_product = models.ForeignKey(
        "inventory.Product", on_delete=models.SET_NULL, null=True, blank=True,
        help_text="The fabric product used, if provided by the shop rather than the customer.",
    )
    order_date = models.DateField()
    expected_delivery_date = models.DateField()
    delivered_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    # Set once services.create_tailoring_order() invoices it — same
    # Uses the same linked-product billing pattern as verticals.gym.GymMember.
    sales_invoice = models.OneToOneField(
        "sales.SalesInvoice", on_delete=models.SET_NULL, null=True, blank=True,
    )

    def __str__(self):
        return f"{self.customer.name} - {self.get_status_display()} (due {self.expected_delivery_date})"
