from django.db import models
from apps.tenants.models import TenantScopedModel


class SaloonService(TenantScopedModel):
    name = models.CharField(max_length=150)  # "Haircut", "Beard Trim", "Hair Color", ...
    duration_minutes = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="saloon_service",
        help_text="The service Product that book_appointment() invoices a walk-in against — see saloon.services.create_saloon_service.",
    )

    def __str__(self):
        return self.name


class ServicePackage(TenantScopedModel):
    name = models.CharField(max_length=150)
    service = models.ForeignKey(SaloonService, on_delete=models.PROTECT, related_name="packages")
    session_count = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="saloon_service_package",
        help_text="The service Product that purchase_package() invoices against — see saloon.services.create_service_package.",
    )

    def __str__(self):
        return f"{self.name} ({self.session_count}x {self.service.name})"


class CustomerPackage(TenantScopedModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="saloon_packages")
    package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT)
    purchased_on = models.DateField()
    sessions_remaining = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.customer.name} - {self.package.name} ({self.sessions_remaining} left)"


class Appointment(TenantScopedModel):
    STATUS = [
        ("booked", "Booked"), ("completed", "Completed"),
        ("cancelled", "Cancelled"), ("no_show", "No Show"),
    ]

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="saloon_appointments")
    service = models.ForeignKey(SaloonService, on_delete=models.PROTECT)
    stylist = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="saloon_appointments")
    customer_package = models.ForeignKey(CustomerPackage, on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS, default="booked")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.customer.name} - {self.service.name} ({self.scheduled_at:%Y-%m-%d %H:%M})"


class ServiceClientProfile(TenantScopedModel):
    """Flexible subject record: patient, student, pet, vehicle, laundry order owner, etc."""
    PROFILE_TYPES = [("person", "Person / Patient"), ("student", "Student"), ("pet", "Pet"),
                     ("vehicle", "Vehicle"), ("asset", "Asset / Item"), ("organization", "Organization")]
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="service_profiles")
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPES, default="person")
    subject_name = models.CharField(max_length=200)
    reference_code = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    identifier = models.CharField(max_length=100, blank=True, help_text="MRN, student ID, plate, asset tag, etc.")
    details = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "reference_code")


class ServiceCase(TenantScopedModel):
    STATUS = [("open", "Open"), ("in_progress", "In Progress"), ("waiting", "Waiting"),
              ("completed", "Completed"), ("cancelled", "Cancelled")]
    profile = models.ForeignKey(ServiceClientProfile, on_delete=models.PROTECT, related_name="cases")
    title = models.CharField(max_length=200)
    case_type = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    assigned_staff = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS, default="open")
    opened_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)


class ServiceCaseNote(TenantScopedModel):
    case = models.ForeignKey(ServiceCase, on_delete=models.CASCADE, related_name="case_notes")
    date = models.DateField()
    note_type = models.CharField(max_length=50, blank=True, help_text="Diagnosis, lesson, repair update, collection, etc.")
    notes = models.TextField()
    outcome = models.TextField(blank=True)
    next_follow_up = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
