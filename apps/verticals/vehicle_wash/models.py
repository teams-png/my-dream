from django.db import models
from apps.tenants.models import TenantScopedModel


class Vehicle(TenantScopedModel):
    VEHICLE_TYPE = [
        ("car", "Car"), ("suv", "SUV"), ("truck", "Truck"), ("bike", "Bike"), ("other", "Other"),
    ]
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="vehicles")
    vehicle_number = models.CharField(max_length=30)  # registration plate
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE, default="car")
    make = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=30, blank=True)

    class Meta:
        unique_together = ("company", "vehicle_number")

    def __str__(self):
        return f"{self.vehicle_number} ({self.customer.name})"


class WashPackage(TenantScopedModel):
    """A wash tier (Basic/Premium/Full Detail), priced per vehicle type."""
    name = models.CharField(max_length=100)
    vehicle_type = models.CharField(max_length=20, choices=Vehicle.VEHICLE_TYPE, default="car")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField(default=30)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="wash_package",
        help_text="The service Product that complete_wash() invoices against — see vehicle_wash.services.create_wash_package.",
    )

    def __str__(self):
        return f"{self.name} ({self.get_vehicle_type_display()})"


class WashOrder(TenantScopedModel):
    STATUS = [
        ("booked", "Booked"), ("in_progress", "In Progress"),
        ("completed", "Completed"), ("cancelled", "Cancelled"),
    ]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="wash_orders")
    package = models.ForeignKey(WashPackage, on_delete=models.PROTECT)
    staff = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="wash_orders",
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS, default="booked")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30, default="cash")
    # Set once services.complete_wash() invoices it — a wash is billed on
    # completion (not at booking, unlike spa/saloon), see services.py.
    sales_invoice = models.OneToOneField(
        "sales.SalesInvoice", on_delete=models.SET_NULL, null=True, blank=True,
    )

    def __str__(self):
        return f"{self.vehicle.vehicle_number} - {self.package.name} ({self.status})"
