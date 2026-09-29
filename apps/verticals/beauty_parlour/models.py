from django.db import models
from apps.tenants.models import TenantScopedModel


class BeautyService(TenantScopedModel):
    """"Facial", "Bridal Makeup", "Hair Spa", "Manicure", ... — same shape as saloon.SaloonService."""
    name = models.CharField(max_length=150)
    duration_minutes = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="beauty_service",
        help_text="The service Product that book_appointment() invoices a walk-in against — see beauty_parlour.services.create_beauty_service.",
    )

    def __str__(self):
        return self.name


class ServicePackage(TenantScopedModel):
    """A bundle of sessions sold upfront (e.g. "3x Bridal Package"), consumed one Appointment at a time."""
    name = models.CharField(max_length=150)
    service = models.ForeignKey(BeautyService, on_delete=models.PROTECT, related_name="packages")
    session_count = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="beauty_service_package",
        help_text="The service Product that purchase_package() invoices against — see beauty_parlour.services.create_service_package.",
    )

    def __str__(self):
        return f"{self.name} ({self.session_count}x {self.service.name})"


class CustomerPackage(TenantScopedModel):
    """A specific customer's purchased package and how many sessions remain."""
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="beauty_packages")
    package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT)
    purchased_on = models.DateField()
    sessions_remaining = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.customer.name} - {self.package.name} ({self.sessions_remaining} left)"


class Appointment(TenantScopedModel):
    """
    Same shape as saloon.Appointment (customer, service, staff, optional package
    redemption, commission on completion). Section 12 of Phase 1 also lists "Product
    sales" for Beauty Parlour — that is retail product sales (creams, cosmetics),
    which is already covered by the core sales + inventory apps (Phase 8/9) once
    they are wired up (see the invoice TODO in services.py) — no separate model
    needed here, to avoid duplicating Product/Invoice.
    """
    STATUS = [
        ("booked", "Booked"), ("completed", "Completed"),
        ("cancelled", "Cancelled"), ("no_show", "No Show"),
    ]

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="beauty_appointments")
    service = models.ForeignKey(BeautyService, on_delete=models.PROTECT)
    beautician = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="beauty_appointments")
    customer_package = models.ForeignKey(CustomerPackage, on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS, default="booked")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.customer.name} - {self.service.name} ({self.scheduled_at:%Y-%m-%d %H:%M})"
