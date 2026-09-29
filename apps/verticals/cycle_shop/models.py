from django.db import models
from apps.tenants.models import TenantScopedModel


class CycleUnit(TenantScopedModel):
    """
    Same reasoning as apps.verticals.mobile_shop.MobileUnit: a serial
    number identifies one physical cycle, so this is one row per unit, not
    per Product/model. Brands, Models, and Accessories (Phase 1 Section 12)
    are already covered by inventory.Product/Brand — this only adds what's
    genuinely per-unit (serial number, warranty, sale tracking).
    """
    STATUS = [("in_stock", "In Stock"), ("sold", "Sold"), ("returned", "Returned")]

    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="cycle_units")
    serial_number = models.CharField(max_length=50)
    warranty_months = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default="in_stock")

    sold_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sold_date = models.DateField(null=True, blank=True)
    buyer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="cycle_units_bought",
    )

    class Meta:
        unique_together = ("company", "serial_number")

    def __str__(self):
        return f"{self.product.name} - #{self.serial_number} ({self.status})"


class ServiceTicket(TenantScopedModel):
    """
    Repair/maintenance workshop ticket — for a cycle bought here
    (`cycle_unit` set) or brought in from elsewhere (left null, described
    in `cycle_description` instead).
    """
    STATUS = [
        ("received", "Received"), ("in_progress", "In Progress"),
        ("completed", "Completed"), ("delivered", "Delivered"),
    ]

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="service_tickets")
    cycle_unit = models.ForeignKey(CycleUnit, on_delete=models.SET_NULL, null=True, blank=True)
    cycle_description = models.CharField(max_length=255, blank=True)
    issue_description = models.TextField()
    staff = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="service_tickets",
    )
    received_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="received")
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivered_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.customer.name} - {self.get_status_display()} ({self.received_date})"
