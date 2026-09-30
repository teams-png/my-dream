from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel

RATE_UNITS = [("hour", "Per hour"), ("day", "Per day"), ("night", "Per night"), ("month", "Per month"),
              ("event", "Per booking")]


# ----------------------------------------------------------------- bookings

class BookableResource(TenantScopedModel):
    """A room, vehicle, piece of equipment, hall or desk that customers book by time."""
    KINDS = [("room", "Room"), ("vehicle", "Vehicle"), ("equipment", "Equipment"), ("hall", "Hall"),
             ("space", "Space / desk"), ("other", "Other")]
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KINDS, default="other")
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rate_unit = models.CharField(max_length=8, choices=RATE_UNITS, default="day")
    capacity = models.PositiveSmallIntegerField(default=1, help_text="Guests / seats (0 = not relevant).")
    details = models.CharField(max_length=255, blank=True, help_text="e.g. plate number, floor, size, features.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="Service product used on invoices; created automatically.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Booking(TenantScopedModel):
    STATUS = [("reserved", "Reserved"), ("checked_in", "Checked in"), ("completed", "Completed"),
              ("cancelled", "Cancelled"), ("no_show", "No-show")]
    ACTIVE = ("reserved", "checked_in")
    number = models.CharField(max_length=20, blank=True)
    resource = models.ForeignKey(BookableResource, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    guests = models.PositiveSmallIntegerField(default=1)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    rate_unit = models.CharField(max_length=8, choices=RATE_UNITS)
    advance = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                  help_text="Paid in advance; applied to the invoice at check-out.")
    advance_method = models.CharField(max_length=10, default="cash")
    advance_date = models.DateField(null=True, blank=True)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="Refundable; held and returned, not income.")
    deposit_returned = models.BooleanField(default=False)
    extras = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extras_note = models.CharField(max_length=255, blank=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=STATUS, default="reserved")
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start"]
        indexes = [models.Index(fields=["company", "resource", "start"]), models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.number or f"Booking {self.pk}"


# ----------------------------------------------------------------- sell by weight

class ScaleSettings(TenantScopedModel):
    """
    How the shop's weighing scale prints its EAN-13 labels, e.g. 21 00123 01250 7:
    prefix "21", item code "00123", value "01250" (1.250 kg or 12.50 price), check digit.
    """
    VALUE_TYPES = [("weight", "Weight (kg)"), ("price", "Price")]
    prefixes = models.CharField(max_length=60, default="20,21,22,23,24,25,26,27,28,29",
                                help_text="Barcode prefixes the scale uses, comma separated.")
    code_digits = models.PositiveSmallIntegerField(default=5, help_text="Digits of the item code after the prefix.")
    value_type = models.CharField(max_length=8, choices=VALUE_TYPES, default="weight")
    value_decimals = models.PositiveSmallIntegerField(default=3, help_text="3 = grams (weight), 2 = cents (price).")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company"], name="one_scale_setting_per_company")]

    @classmethod
    def load(cls, company):
        obj, _ = cls.objects.get_or_create(company=company)
        return obj

    def as_dict(self):
        return {"prefixes": [p.strip() for p in self.prefixes.split(",") if p.strip()], "codeDigits": self.code_digits,
                "valueType": self.value_type, "decimals": self.value_decimals}


# ----------------------------------------------------------------- education

class Course(TenantScopedModel):
    """A course, class or batch students enrol in (or a driving package)."""
    BILLING = [("monthly", "Monthly fee"), ("once", "One-time fee")]
    name = models.CharField(max_length=150)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing = models.CharField(max_length=8, choices=BILLING, default="monthly")
    schedule = models.CharField(max_length=150, blank=True, help_text="e.g. Sun–Thu 4–6 pm")
    teacher = models.CharField(max_length=120, blank=True)
    capacity = models.PositiveSmallIntegerField(default=0, help_text="0 = no limit")
    is_active = models.BooleanField(default=True)
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Enrollment(TenantScopedModel):
    STATUS = [("active", "Active"), ("completed", "Completed"), ("withdrawn", "Withdrawn")]
    student = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    guardian_name = models.CharField(max_length=120, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["student__name"]

    def __str__(self):
        return f"{self.student} · {self.course}"

    @property
    def fee(self):
        from decimal import Decimal
        return (self.course.fee * (Decimal("100") - self.discount_percent) / Decimal("100")).quantize(Decimal("0.01"))


class FeeCharge(TenantScopedModel):
    """One billed fee: a month ("2026-10") or the one-time fee ("once") of an enrollment."""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="charges")
    period = models.CharField(max_length=7)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["enrollment", "period"], name="one_fee_per_enrollment_period")]


class AttendanceSession(TenantScopedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField()
    taken_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "date"], name="one_attendance_per_course_day")]
        ordering = ["-date"]


class Property(TenantScopedModel):
    KINDS = [("building", "Building"), ("villa", "Villa / house"), ("compound", "Compound"),
             ("commercial", "Commercial"), ("land", "Land / yard")]
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=12, choices=KINDS, default="building")
    address = models.CharField(max_length=255, blank=True)
    owner_name = models.CharField(max_length=150, blank=True, help_text="Landlord, if you manage it for someone else.")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "properties"

    def __str__(self):
        return self.name


class RentalUnit(TenantScopedModel):
    KINDS = [("apartment", "Apartment / flat"), ("villa", "Villa"), ("room", "Room / bed space"), ("shop", "Shop"),
             ("office", "Office"), ("warehouse", "Warehouse"), ("other", "Other")]
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=KINDS, default="apartment")
    bedrooms = models.PositiveSmallIntegerField(default=0)
    size = models.CharField(max_length=40, blank=True, help_text="e.g. 120 m²")
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["property__name", "name"]

    def __str__(self):
        return f"{self.property.name} · {self.name}"


class Lease(TenantScopedModel):
    STATUS = [("active", "Active"), ("ended", "Ended"), ("terminated", "Terminated early")]
    number = models.CharField(max_length=20, blank=True)
    unit = models.ForeignKey(RentalUnit, on_delete=models.PROTECT, related_name="leases")
    tenant = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)
    due_day = models.PositiveSmallIntegerField(default=1, help_text="Day of the month rent is due (1–28).")
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_returned = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS, default="active")
    ended_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.number or f"Lease {self.pk}"


class RentCharge(TenantScopedModel):
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="charges")
    period = models.CharField(max_length=7)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period"]
        constraints = [models.UniqueConstraint(fields=["lease", "period"], name="one_rent_per_lease_month")]


class AttendanceMark(models.Model):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="marks")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance")
    present = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "enrollment"], name="one_mark_per_student_session")]
