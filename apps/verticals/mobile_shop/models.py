from django.db import models
from apps.tenants.models import TenantScopedModel


class MobileUnit(TenantScopedModel):
    """
    A mobile shop can't track phones the way a textile shop tracks bolts of
    fabric — every physical handset is unique (IMEI), so unlike
    FabricDetail (one row per Product), this is one row PER PHYSICAL UNIT.
    `product` groups units by model/brand (e.g. "iPhone 13 128GB Blue");
    inventory.Product's own quantity field is not the source of truth for
    a mobile shop — MobileUnit.status is (a unit is either in stock, sold,
    returned, or in repair; there's no "quantity 3" for a single IMEI).
    """
    STATUS = [
        ("in_stock", "In Stock"), ("sold", "Sold"),
        ("returned", "Returned"), ("under_repair", "Under Repair"),
    ]
    CONDITION = [("new", "New"), ("used", "Used"), ("refurbished", "Refurbished")]

    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="mobile_units")
    imei = models.CharField(max_length=20)
    serial_number = models.CharField(max_length=50, blank=True)
    condition = models.CharField(max_length=20, choices=CONDITION, default="new")
    warranty_months = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default="in_stock")

    sold_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sold_date = models.DateField(null=True, blank=True)
    buyer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="mobile_units_bought",
    )
    sale_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="mobile_units",
    )
    warehouse = models.ForeignKey("inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("company", "imei")

    def __str__(self):
        return f"{self.product.name} - IMEI {self.imei} ({self.status})"

    @property
    def warranty_expires(self):
        if self.sold_date and self.warranty_months:
            # Simple month arithmetic, no external date-util dependency.
            month = self.sold_date.month - 1 + self.warranty_months
            year = self.sold_date.year + month // 12
            month = month % 12 + 1
            day = min(self.sold_date.day, 28)
            from datetime import date
            return date(year, month, day)
        return None


class MobileRepairJob(TenantScopedModel):
    STATUS = [("received", "Received"), ("diagnosing", "Diagnosing"), ("waiting_parts", "Waiting for Parts"),
              ("ready", "Ready"), ("completed", "Completed"), ("cancelled", "Cancelled")]
    job_number = models.CharField(max_length=30)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    mobile_unit = models.ForeignKey(MobileUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name="repair_jobs")
    device_description = models.CharField(max_length=255)
    imei = models.CharField(max_length=20, blank=True)
    reported_issue = models.TextField()
    diagnosis = models.TextField(blank=True)
    work_done = models.TextField(blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    final_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="received")
    service_product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.PROTECT)
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    invoice = models.OneToOneField("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL)
    received_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assigned_technician = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="mobile_repair_jobs",
    )
    labour_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    parts_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_warranty_job = models.BooleanField(default=False)

    class Meta:
        unique_together = ("company", "job_number")
        indexes = [models.Index(fields=("company", "status", "received_at"))]


class MobileTradeIn(TenantScopedModel):
    STATUS = [("quoted", "Quoted"), ("accepted", "Accepted"), ("rejected", "Rejected")]
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    imei = models.CharField(max_length=20)
    serial_number = models.CharField(max_length=50, blank=True)
    condition = models.CharField(max_length=20, choices=MobileUnit.CONDITION, default="used")
    quoted_value = models.DecimalField(max_digits=12, decimal_places=2)
    accepted_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="quoted")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    purchase = models.OneToOneField("purchases.Purchase", null=True, blank=True, on_delete=models.SET_NULL)
    mobile_unit = models.OneToOneField(MobileUnit, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "imei")


class MobileRepairPart(TenantScopedModel):
    job = models.ForeignKey(MobileRepairJob, on_delete=models.CASCADE, related_name="parts")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class MobileWarrantyClaim(TenantScopedModel):
    STATUS = [("received", "Received"), ("submitted", "Submitted"), ("approved", "Approved"),
              ("rejected", "Rejected"), ("resolved", "Resolved")]
    claim_number = models.CharField(max_length=30)
    unit = models.ForeignKey(MobileUnit, on_delete=models.PROTECT, related_name="warranty_claims")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    issue = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="received")
    resolution = models.TextField(blank=True)
    received_date = models.DateField()
    resolved_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("company", "claim_number")


class MobileInstallmentPlan(TenantScopedModel):
    FREQUENCY = [("weekly", "Weekly"), ("monthly", "Monthly")]
    STATUS = [("active", "Active"), ("paid", "Paid"), ("overdue", "Overdue"), ("cancelled", "Cancelled")]
    invoice = models.OneToOneField("sales.SalesInvoice", on_delete=models.PROTECT, related_name="mobile_installment")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    financed_amount = models.DecimalField(max_digits=14, decimal_places=2)
    deposit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    installment_count = models.PositiveIntegerField(default=1)
    frequency = models.CharField(max_length=10, choices=FREQUENCY, default="monthly")
    next_due_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amount_paid(self):
        from django.db.models import Sum
        return self.payments.aggregate(t=Sum("amount"))["t"] or 0

    @property
    def outstanding(self):
        return max(self.financed_amount - self.amount_paid, 0)


class MobileInstallmentPayment(TenantScopedModel):
    plan = models.ForeignKey(MobileInstallmentPlan, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=20, default="cash")
    customer_payment = models.OneToOneField("sales.CustomerPayment", null=True, blank=True, on_delete=models.SET_NULL)
