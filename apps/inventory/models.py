from django.db import models
from apps.tenants.models import TenantScopedModel


class ProductCategory(TenantScopedModel):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Brand(TenantScopedModel):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Unit(TenantScopedModel):
    name = models.CharField(max_length=30)   # "pcs", "kg", "meter"

    def __str__(self):
        return self.name


class Warehouse(TenantScopedModel):
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    manager_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(TenantScopedModel):
    TRACKING = [("none", "None"), ("basic", "Basic Stock"), ("batch", "Batch/Lot"), ("serial", "Serial Number")]

    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_stock_tracked = models.BooleanField(
        default=True,
        help_text=(
            "False for service-type products (gym memberships, spa sessions, ...) that get "
            "invoiced through sales.services.create_invoice() but have no physical stock to "
            "move. When False: create_invoice()/process_return() skip writing a StockMovement "
            "for this product, and it's excluded from reports.stock_report and the low-stock "
            "notification sweep. See docs/phase1-database-design.md — introduced to fix the "
            "'service product drifts negative in stock reports' quirk flagged in the gym and "
            "spa vertical notes."
        ),
    )
    tracking_type = models.CharField(
        max_length=10, choices=TRACKING, default="basic",
        help_text=(
            "Phase 31: how granularly this product's stock is tracked. Only meaningful when "
            "is_stock_tracked=True — ignored (treated as 'none') for service products. "
            "'basic' is the pre-Phase-31 behaviour (aggregate quantity only, what every "
            "existing product effectively had). 'batch' requires selecting/recording a "
            "ProductBatch on every stock movement; 'serial' requires a ProductSerial."
        ),
    )
    block_expired_batch_sale = models.BooleanField(
        default=True,
        help_text="Batch-tracked products only: if True, selling from a batch whose expiry_date "
                   "has passed is rejected outright rather than just warned about.",
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="variants",
        help_text="Set if this row is a variant (e.g. a specific size/color) of another product.",
    )
    variant_label = models.CharField(
        max_length=100, blank=True, help_text="e.g. 'Red / M' — only meaningful when parent is set.",
    )
    size = models.CharField(max_length=50, blank=True, db_index=True)
    colour = models.CharField(max_length=50, blank=True, db_index=True)
    material = models.CharField(max_length=100, blank=True)
    design = models.CharField(max_length=100, blank=True)
    attributes = models.JSONField(
        default=dict, blank=True,
        help_text="Free-form spec details (material, warranty, weight...) as key/value pairs.",
    )

    class Meta:
        unique_together = ("company", "sku")

    def __str__(self):
        return self.name

    def current_stock(self, warehouse=None):
        """Derived from the StockMovement ledger — never a stored counter (Phase 0 Section 18)."""
        from django.db.models import Sum
        qs = self.movements.all()
        if warehouse:
            qs = qs.filter(warehouse=warehouse)
        return qs.aggregate(total=Sum("quantity"))["total"] or 0

    def save(self, *args, **kwargs):
        if self.parent_id and not self.variant_label:
            self.variant_label = " / ".join(v for v in (self.colour, self.size) if v)
        super().save(*args, **kwargs)


class ProductBatch(TenantScopedModel):
    """
    A manufactured lot/batch of a `tracking_type='batch'` product. Stock
    held in this batch is never a stored quantity here — it's derived by
    summing StockMovement rows carrying this batch (same append-only-
    ledger principle as Product.current_stock()), so "batch stock
    reconciles by warehouse" by construction rather than needing separate
    reconciliation logic.
    """
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=100)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "product", "batch_number")
        ordering = ["expiry_date"]

    def __str__(self):
        return f"{self.product.name} · {self.batch_number}"


class ProductSerial(TenantScopedModel):
    """
    One physical unit of a `tracking_type='serial'` product (IMEI, engine
    number, ...). `status` plus the (company, product, serial_number)
    uniqueness together are what make "serial number cannot be sold
    twice" hold: selling flips status to 'sold', and services.py refuses
    to sell (or re-register) a serial that isn't 'in_stock'.
    """
    STATUS = [("in_stock", "In Stock"), ("sold", "Sold"), ("returned", "Returned")]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="serials")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    serial_number = models.CharField(max_length=150)
    status = models.CharField(max_length=10, choices=STATUS, default="in_stock")
    received_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "product", "serial_number")

    def __str__(self):
        return f"{self.product.name} · {self.serial_number}"


class StockMovement(TenantScopedModel):
    REASON = [
        ("purchase", "Purchase"), ("sale", "Sale"), ("adjustment", "Adjustment"),
        ("transfer_in", "Transfer In"), ("transfer_out", "Transfer Out"), ("return", "Return"),
        ("stock_count", "Stock Count Adjustment"), ("goods_receipt", "Goods Receipt (PO)"),
        ("delivery", "Delivery (Sales Order)"),
    ]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)  # signed: + in, - out
    reason = models.CharField(max_length=20, choices=REASON)
    reference = models.CharField(max_length=100, blank=True)
    batch = models.ForeignKey(
        ProductBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="movements",
        help_text="Phase 31: set only for tracking_type='batch' products. Existing rows from "
                   "before this phase are NULL, and aggregate current_stock() sums regardless.",
    )
    serial = models.ForeignKey(
        ProductSerial, null=True, blank=True, on_delete=models.PROTECT, related_name="movements",
        help_text="Phase 31: set only for tracking_type='serial' products (always ±1 quantity).",
    )
    moved_at = models.DateTimeField(auto_now_add=True)

    def batch_warehouse_balance(self):
        """Sum of this batch's movements in this specific warehouse — the
        'batch stock reconciles by warehouse' figure, computed the same
        way anywhere it's needed rather than duplicated per caller."""
        from django.db.models import Sum
        if not self.batch_id:
            return None
        return StockMovement.objects.filter(
            company=self.company, batch=self.batch, warehouse=self.warehouse
        ).aggregate(total=Sum("quantity"))["total"] or 0


class StockCount(TenantScopedModel):
    """A physical stock count session for one warehouse. Lines are
    snapshotted at start; completing the count posts a reconciling
    StockMovement per line with a variance, and always writes an
    AuditLog entry (Phase 31 acceptance criteria: 'stock-count
    adjustment leaves an audit trail')."""
    STATUS = [("draft", "Draft"), ("completed", "Completed")]

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    completed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StockCountLine(models.Model):
    stock_count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    system_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    counted_quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    @property
    def variance(self):
        if self.counted_quantity is None:
            return None
        return self.counted_quantity - self.system_quantity


class BatchAlertLog(TenantScopedModel):
    """Dedup marker so near-expiry/expired notifications fire once per
    (batch, alert type) — same fix as Phase 30's overdue-invoice spam,
    applied here before it ships with the same bug."""
    ALERT_TYPE = [("near_expiry", "Near Expiry"), ("expired", "Expired")]

    batch = models.ForeignKey(ProductBatch, on_delete=models.CASCADE, related_name="alert_logs")
    alert_type = models.CharField(max_length=15, choices=ALERT_TYPE)
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "batch", "alert_type")
