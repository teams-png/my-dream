from decimal import Decimal
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
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
    """A job card / appointment: booked or walked in → in progress → (waiting) → ready → completed (billed)."""
    STATUS = [("open", _("Booked / to start")), ("in_progress", _("In progress")), ("waiting", _("Waiting")),
              ("ready", _("Ready")), ("completed", _("Completed")), ("cancelled", _("Cancelled"))]
    PRIORITY = [("normal", _("Normal")), ("urgent", _("Urgent"))]
    number = models.CharField(max_length=20, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Appointment time")
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    ready_by = models.DateTimeField(null=True, blank=True, help_text="Promised to the customer")
    priority = models.CharField(max_length=10, choices=PRIORITY, default="normal")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    contract = models.ForeignKey("ServiceContract", null=True, blank=True, on_delete=models.SET_NULL, related_name="visits")
    record = models.JSONField(default=dict, blank=True)  # clinic visit / lab results / eye test / laundry details
    visit_no = models.PositiveSmallIntegerField(default=0)
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


class ServiceCaseLine(TenantScopedModel):
    """A part or a labour/service charge on a job card. Billed together when the job is done."""
    KINDS = [("part", _("Part / item")), ("labour", _("Labour / service"))]
    case = models.ForeignKey(ServiceCase, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=10, choices=KINDS, default="labour")
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class TechnicianLink(TenantScopedModel):
    """A staff member's private phone page for their jobs (no login)."""
    employee = models.OneToOneField("employees.Employee", on_delete=models.CASCADE, related_name="technician_link")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ServiceContract(TenantScopedModel):
    """A maintenance / service contract (AMC): visits are planned by themselves as job cards, and it is billed
    up front, every month / 3 months / year (as a recurring invoice) or per visit."""
    EVERY = [("weekly", _("Every week")), ("fortnightly", _("Every 2 weeks")), ("monthly", _("Every month")),
             ("bimonthly", _("Every 2 months")), ("quarterly", _("Every 3 months")), ("four_monthly", _("Every 4 months")),
             ("half_yearly", _("Every 6 months")), ("yearly", _("Once a year"))]
    BILLING = [("upfront", _("Full amount up front")), ("monthly", _("Every month")), ("quarterly", _("Every 3 months")),
               ("yearly", _("Every year")), ("per_visit", _("Per visit")), ("none", _("No bill from here"))]
    STATUS = [("active", _("Active")), ("paused", _("Paused")), ("ended", _("Ended")), ("cancelled", _("Cancelled"))]
    number = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="service_contracts")
    profile = models.ForeignKey(ServiceClientProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="contracts")
    title = models.CharField(max_length=200)
    site_address = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    visit_every = models.CharField(max_length=15, choices=EVERY, default="quarterly")
    next_visit_date = models.DateField(null=True, blank=True)
    preferred_time = models.TimeField(null=True, blank=True)
    visit_minutes = models.PositiveSmallIntegerField(default=60)
    staff = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    visit_task = models.TextField(blank=True, help_text=_("What to do on every visit (checklist)"))
    contract_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing = models.CharField(max_length=10, choices=BILLING, default="upfront")
    bill_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                      help_text=_("Per bill (or per visit)"))
    recurring = models.ForeignKey("finance.RecurringInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    upfront_invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=STATUS, default="active", db_index=True)
    renewed_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["end_date", "id"]

    def __str__(self):
        return f"{self.number} {self.title}"
