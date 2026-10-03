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


class GoldRate(TenantScopedModel):
    """The shop's selling rate per gram for a karat on a day (the latest one applies)."""
    KARATS = [("24K", "24K"), ("22K", "22K"), ("21K", "21K"), ("18K", "18K")]
    karat = models.CharField(max_length=4, choices=KARATS)
    date = models.DateField()
    rate_per_gram = models.DecimalField(max_digits=12, decimal_places=2)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "karat"]
        constraints = [models.UniqueConstraint(fields=["company", "karat", "date"], name="one_gold_rate_per_karat_day")]


class AttendanceMark(models.Model):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="marks")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance")
    present = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "enrollment"], name="one_mark_per_student_session")]


# ------------------------------------------------------------------ recruitment

class JobOrder(TenantScopedModel):
    """A client's demand: how many people, for which position, on what terms."""
    STATUS = [("open", "Open"), ("on_hold", "On hold"), ("filled", "Filled"), ("closed", "Closed")]
    GENDER = [("any", "Any"), ("male", "Male"), ("female", "Female")]
    number = models.CharField(max_length=20, blank=True)
    client = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="job_orders")
    position = models.CharField(max_length=150)
    vacancies = models.PositiveIntegerField(default=1)
    work_location = models.CharField(max_length=150, blank=True)
    nationality = models.CharField(max_length=100, blank=True, help_text="Preferred nationality, if any.")
    gender = models.CharField(max_length=10, choices=GENDER, default="any")
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    benefits = models.CharField(max_length=255, blank=True, help_text="Accommodation, food, transport…")
    requirements = models.TextField(blank=True)
    contract_months = models.PositiveIntegerField(null=True, blank=True)
    fee_per_placement = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    guarantee_days = models.PositiveIntegerField(default=90, help_text="Free replacement period after joining.")
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    publish_online = models.BooleanField(default=False, help_text="Show this job on the careers website.")
    public_summary = models.TextField(blank=True, help_text="What job seekers see. The client's name is never shown.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.position}"


class Candidate(TenantScopedModel):
    STATUS = [("available", "Available"), ("in_process", "In process"), ("placed", "Placed"),
              ("not_suitable", "Not suitable")]
    GENDER = [("", "—"), ("male", "Male"), ("female", "Female")]
    number = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    passport_no = models.CharField(max_length=30, blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    trade = models.CharField(max_length=150, blank=True, help_text="Position / skill, e.g. Electrician, Driver, Nurse.")
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    gulf_experience = models.BooleanField(default=False)
    current_location = models.CharField(max_length=150, blank=True)
    expected_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    languages = models.CharField(max_length=150, blank=True)
    education = models.CharField(max_length=150, blank=True)
    agent = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="candidates", help_text="Sub-agent who sent this candidate.")
    cv = models.FileField(upload_to="recruitment/cv/%Y/%m/", blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="available")
    SOURCES = [("office", "Office"), ("website", "Website"), ("agent", "Sub-agent"), ("referral", "Referral")]
    source = models.CharField(max_length=10, choices=SOURCES, default="office")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                 help_text="Billing record when the candidate pays a fee.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Placement(TenantScopedModel):
    """One candidate put forward for one job order, followed until they join (or drop out)."""
    STAGES = [("applied", "Applied online"), ("submitted", "CV sent"), ("shortlisted", "Shortlisted"), ("interview", "Interview"),
              ("selected", "Selected"), ("medical", "Medical"), ("visa", "Visa"), ("ticket", "Ticket"),
              ("deployed", "Joined / deployed"), ("rejected", "Rejected"), ("withdrawn", "Withdrawn")]
    ACTIVE = ["applied", "submitted", "shortlisted", "interview", "selected", "medical", "visa", "ticket"]
    MEDICAL = [("", "—"), ("pending", "Pending"), ("fit", "Fit"), ("unfit", "Unfit")]
    job_order = models.ForeignKey(JobOrder, on_delete=models.CASCADE, related_name="placements")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="placements")
    stage = models.CharField(max_length=12, choices=STAGES, default="submitted")
    interview_at = models.DateTimeField(null=True, blank=True)
    offered_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    medical_date = models.DateField(null=True, blank=True)
    medical_result = models.CharField(max_length=10, choices=MEDICAL, blank=True)
    visa_number = models.CharField(max_length=50, blank=True)
    visa_expiry = models.DateField(null=True, blank=True)
    ticket_date = models.DateField(null=True, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    guarantee_until = models.DateField(null=True, blank=True)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    candidate_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    candidate_invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job_order", "candidate"], name="one_placement_per_job_candidate")]
        ordering = ["-updated_at"]

    @property
    def is_active(self):
        return self.stage in self.ACTIVE


class PlacementCost(TenantScopedModel):
    TYPES = [("medical", "Medical"), ("visa", "Visa"), ("ticket", "Air ticket"), ("agent", "Agent commission"),
             ("documents", "Documents / attestation"), ("other", "Other")]
    placement = models.ForeignKey(Placement, on_delete=models.CASCADE, related_name="costs")
    cost_type = models.CharField(max_length=12, choices=TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    paid_to = models.CharField(max_length=150, blank=True)
    expense = models.ForeignKey("expenses.Expense", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class CareersSite(TenantScopedModel):
    """A recruitment agency's public website: who they are, open jobs and an apply form.
    Applications land in that agency's own candidates and job pipelines only."""
    enabled = models.BooleanField(default=False)
    slug = models.SlugField(max_length=60, unique=True)
    headline = models.CharField(max_length=200, blank=True)
    about = models.TextField(blank=True)
    services = models.TextField(blank=True, help_text="One per line.")
    countries = models.CharField(max_length=255, blank=True, help_text="Countries you recruit for, e.g. Qatar, UAE, Saudi Arabia.")
    whatsapp = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    licence = models.CharField(max_length=120, blank=True, help_text="Recruitment licence number, shown in the footer.")
    accent_color = models.CharField(max_length=7, default="#0f766e")
    ask_passport = models.BooleanField(default=True)
    allowed_origins = models.TextField(blank=True, help_text="Your own website addresses that may send applications, one per line.")
    api_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.slug


# ------------------------------------------------------------------ online booking (website / WordPress)

class BookingSite(TenantScopedModel):
    """A business's online booking form: on its own website (widget / WordPress plugin) or a BookPilot page."""
    slug = models.SlugField(max_length=60, unique=True)
    enabled = models.BooleanField(default=True)
    headline = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=255, blank=True, help_text="Shown above the form, e.g. opening hours.")
    accent_color = models.CharField(max_length=7, default="#0f766e")
    whatsapp = models.CharField(max_length=30, blank=True)
    min_notice_hours = models.PositiveSmallIntegerField(default=1)
    max_days_ahead = models.PositiveSmallIntegerField(default=90)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.slug


class OnlineBooking(TenantScopedModel):
    """A booking request from the website. Staff confirm it, which creates the real appointment / booking / table."""
    KINDS = [("appointment", "Appointment"), ("resource", "Booking"), ("table", "Table reservation"), ("event", "Event enquiry")]
    STATUS = [("new", "New"), ("confirmed", "Confirmed"), ("declined", "Declined"), ("cancelled", "Cancelled")]
    number = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    item_id = models.PositiveIntegerField(null=True, blank=True, help_text="Service or resource chosen.")
    item_name = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    guests = models.PositiveSmallIntegerField(default=1)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=120, blank=True)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    linked = models.CharField(max_length=40, blank=True, help_text="What it became, e.g. booking:12 or reservation:4.")
    reply = models.CharField(max_length=255, blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.number or f"Request {self.pk}"


# ------------------------------------------------------------------ website kit (platform admin builds client sites)

class WebsiteKit(TenantScopedModel):
    """Everything a client's own website (WordPress / HTML / Python) needs to talk to BookPilot.
    public_id is safe to put in page source; api_key is only for server-to-server calls."""
    public_id = models.SlugField(max_length=60, unique=True)
    api_key = models.CharField(max_length=48, unique=True)
    allowed_origins = models.TextField(blank=True, help_text="Client website addresses, one per line.")
    connected_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_check = models.CharField(max_length=255, blank=True)
    last_check_ok = models.BooleanField(default=False)
    enquiry_enabled = models.BooleanField(default=True)
    accent_color = models.CharField(max_length=7, default="#0f766e")
    notes = models.TextField(blank=True, help_text="Admin notes: hosting, logins, domain…")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.public_id


class SiteDesign(TenantScopedModel):
    """A ready-made website hosted by BookPilot for a business. Menu / services / rooms / jobs, offers and
    contact details come live from the business's own BookPilot data; the owner picks the look."""
    THEMES = [("fresh", "Fresh"), ("bold", "Bold"), ("elegant", "Elegant"), ("minimal", "Minimal")]
    FONTS = [("Inter", "Inter"), ("Poppins", "Poppins"), ("Playfair Display", "Playfair Display"),
             ("Cairo", "Cairo (Arabic)"), ("Lora", "Lora"), ("Montserrat", "Montserrat")]
    DOMAIN_STATUS = [("", "No own domain"), ("pending", "Waiting for DNS"), ("live", "Live")]

    enabled = models.BooleanField(default=False, help_text="Website add-on switched on by the platform admin.")
    published = models.BooleanField(default=False)
    theme = models.CharField(max_length=12, choices=THEMES, default="fresh")
    font = models.CharField(max_length=30, choices=FONTS, default="Poppins")
    primary_color = models.CharField(max_length=7, default="#0f766e")
    accent_color = models.CharField(max_length=7, default="#f59e0b")
    logo = models.ImageField(upload_to="site_logos/", blank=True, null=True, help_text="Leave empty to use the company logo.")
    hero_image = models.ImageField(upload_to="site_heroes/", blank=True, null=True)
    hero_title = models.CharField(max_length=150, blank=True)
    hero_subtitle = models.CharField(max_length=255, blank=True)
    about = models.TextField(blank=True)
    opening_hours = models.TextField(blank=True, help_text="One line per day or range, e.g. Sat–Thu 10am–11pm")
    map_url = models.URLField(blank=True, help_text="Google Maps link")
    whatsapp = models.CharField(max_length=30, blank=True)
    instagram = models.CharField(max_length=120, blank=True)
    facebook = models.CharField(max_length=120, blank=True)
    tiktok = models.CharField(max_length=120, blank=True)
    show_catalogue = models.BooleanField(default=True)
    show_offers = models.BooleanField(default=True)
    show_booking = models.BooleanField(default=True)
    show_careers = models.BooleanField(default=True)
    show_contact = models.BooleanField(default=True)
    # platform admin only
    custom_domain = models.CharField(max_length=253, blank=True, null=True, unique=True)
    domain_status = models.CharField(max_length=10, choices=DOMAIN_STATUS, blank=True, default="")
    custom_css = models.TextField(blank=True)
    custom_html = models.TextField(blank=True, help_text="Extra section shown above the contact section.")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Website · {self.company_id}"
