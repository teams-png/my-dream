from django.db import models
from apps.tenants.models import TenantScopedModel


class Employee(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    role_title = models.CharField(max_length=100, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    joined_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    user = models.OneToOneField("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="employee_profile")
    department = models.ForeignKey("Department", null=True, blank=True, on_delete=models.SET_NULL)
    designation = models.ForeignKey("Designation", null=True, blank=True, on_delete=models.SET_NULL)
    employment_status = models.CharField(max_length=20, choices=[("active", "Active"), ("probation", "Probation"), ("inactive", "Inactive"), ("terminated", "Terminated")], default="active")
    leaving_date = models.DateField(null=True, blank=True)
    shift = models.ForeignKey("WorkShift", null=True, blank=True, on_delete=models.SET_NULL)
    # site workers (manpower supply): people who work at a client's site, not in the office
    WORKER_TYPES = [("office", "Office staff"), ("site", "Site worker")]
    PAY_BASIS = [("monthly", "Monthly salary"), ("daily", "Per day worked"), ("hourly", "Per hour worked")]
    worker_type = models.CharField(max_length=10, choices=WORKER_TYPES, default="office")
    site = models.ForeignKey("WorkSite", null=True, blank=True, on_delete=models.SET_NULL, related_name="workers")
    trade = models.CharField(max_length=100, blank=True)
    nationality = models.CharField(max_length=60, blank=True)
    pay_basis = models.CharField(max_length=10, choices=PAY_BASIS, default="monthly")
    bill_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                    help_text="What the client pays for this worker (empty = the site's rate).")
    accommodation = models.CharField(max_length=120, blank=True)
    candidate = models.ForeignKey("industry.Candidate", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    duty_shift = models.ForeignKey("SiteShift", null=True, blank=True, on_delete=models.SET_NULL, related_name="workers")
    camp = models.ForeignKey("Camp", null=True, blank=True, on_delete=models.SET_NULL, related_name="residents")
    bank_short_name = models.CharField(max_length=10, blank=True)  # for the WPS salary file, e.g. QNB, CBQ
    iban = models.CharField(max_length=34, blank=True)
    visa_id = models.CharField(max_length=30, blank=True)
    weekly_off = models.PositiveSmallIntegerField(null=True, blank=True)  # Python weekday, Mon=0; empty = company's off days

    def __str__(self):
        return self.name


class WorkSite(TenantScopedModel):
    """A client's site where our workers are placed (manpower supply)."""
    BILL_BASIS = [("hour", "Per hour"), ("day", "Per day"), ("month", "Per month")]
    name = models.CharField(max_length=150)
    client = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="work_sites")
    location = models.CharField(max_length=200, blank=True)
    supervisor = models.CharField(max_length=120, blank=True)
    supervisor_phone = models.CharField(max_length=30, blank=True)
    bill_basis = models.CharField(max_length=10, choices=BILL_BASIS, default="hour")
    bill_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ot_bill_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hours_per_day = models.DecimalField(max_digits=4, decimal_places=1, default=8)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SiteShift(TenantScopedModel):
    """A duty shift at a site (Day 6am–6pm, Night…) and how many workers it needs."""
    site = models.ForeignKey(WorkSite, on_delete=models.CASCADE, related_name="shifts")
    name = models.CharField(max_length=60)
    start_time = models.TimeField()
    end_time = models.TimeField()
    needed = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["start_time", "name"]

    def __str__(self):
        return f"{self.name} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    @property
    def hours(self):
        from datetime import datetime, timedelta
        from decimal import Decimal
        start = datetime.combine(datetime.min, self.start_time)
        end = datetime.combine(datetime.min, self.end_time)
        if end <= start:
            end += timedelta(days=1)  # a night shift ends the next morning
        return Decimal(str(round((end - start).seconds / 3600, 2)))


class SiteInvoice(TenantScopedModel):
    """One client bill per site per month, so a month is never billed twice."""
    site = models.ForeignKey(WorkSite, on_delete=models.CASCADE, related_name="invoices")
    month = models.DateField()  # first day of the month
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site", "month"], name="one_bill_per_site_month")]


class Commission(TenantScopedModel):
    """
    Generic — earned by an Employee against any source document (a spa
    Appointment, a saloon service, a beauty-parlour sale, ...), identified
    by reference_type/reference_id rather than a hard FK per vertical, so
    every commission-paying vertical (spa, saloon, beauty parlour — Phase 1
    Section 12) shares one table instead of duplicating it.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="commissions")
    reference_type = models.CharField(max_length=50)  # e.g. "spa.Appointment"
    reference_id = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee.name} - {self.amount} ({self.date})"


class Department(TenantScopedModel):
    name = models.CharField(max_length=120)
    class Meta:
        unique_together = ("company", "name")


class Designation(TenantScopedModel):
    name = models.CharField(max_length=120)
    class Meta:
        unique_together = ("company", "name")


class WorkShift(TenantScopedModel):
    name = models.CharField(max_length=120)
    start_time = models.TimeField()
    end_time = models.TimeField()
    working_days = models.JSONField(default=list, blank=True)


class Attendance(TenantScopedModel):
    STATUS = [("present", "Present"), ("absent", "Absent"), ("half_day", "Half day"), ("leave", "Leave"), ("holiday", "Holiday")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    site = models.ForeignKey("WorkSite", null=True, blank=True, on_delete=models.SET_NULL, related_name="attendance")
    hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ot_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    class Meta:
        unique_together = ("company", "employee", "date")


class LeaveType(TenantScopedModel):
    name = models.CharField(max_length=120)
    paid = models.BooleanField(default=True)
    annual_entitlement = models.DecimalField(max_digits=6, decimal_places=2, default=0)


class LeaveBalance(TenantScopedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    opening = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    used = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    adjustment = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    class Meta:
        unique_together = ("company", "employee", "leave_type", "year")
    @property
    def available(self):
        return self.opening + self.adjustment - self.used


class LeaveRequest(TenantScopedModel):
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.DecimalField(max_digits=6, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_leave_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)


class Holiday(TenantScopedModel):
    name = models.CharField(max_length=120)
    date = models.DateField()
    class Meta:
        unique_together = ("company", "date")


class EmployeeDocument(TenantScopedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=80)
    document_number = models.CharField(max_length=120, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Metadata only: identity-document file bytes are intentionally not stored here.


class DocumentAlertLog(TenantScopedModel):
    document = models.ForeignKey(EmployeeDocument, on_delete=models.CASCADE, related_name="alerts")
    threshold_days = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("company", "document", "threshold_days")


class SalaryStructure(TenantScopedModel):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="salary_structure")
    basic_pay = models.DecimalField(max_digits=14, decimal_places=2)
    allowances = models.JSONField(default=dict, blank=True)
    deductions = models.JSONField(default=dict, blank=True)
    overtime_hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)


class OvertimeEntry(TenantScopedModel):
    TYPE = [("normal", "Normal"), ("weekend", "Weekend"), ("holiday", "Holiday")]
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="overtime_entries")
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    overtime_type = models.CharField(max_length=20, choices=TYPE, default="normal")
    multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_overtime_entries")
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    class Meta:
        unique_together = ("company", "employee", "date", "overtime_type")


class PayrollPeriod(TenantScopedModel):
    name = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    class Meta:
        unique_together = ("company", "start_date", "end_date")


class PayrollRun(TenantScopedModel):
    STATUS = [("draft", "Draft"), ("posted", "Posted"), ("reversed", "Reversed")]
    period = models.OneToOneField(PayrollPeriod, on_delete=models.PROTECT, related_name="payroll_run")
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    total_gross = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_advances = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_payroll_runs")
    posted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="posted_payroll_runs")
    posted_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="payroll_run")
    reversal_journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="reversed_payroll_run")


class PayrollLine(TenantScopedModel):
    PAYMENT = [("unpaid", "Unpaid"), ("paid", "Paid")]
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payroll_lines")
    basic_pay = models.DecimalField(max_digits=14, decimal_places=2)
    allowances = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gross_pay = models.DecimalField(max_digits=14, decimal_places=2)
    net_pay = models.DecimalField(max_digits=14, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=PAYMENT, default="unpaid")
    paid_at = models.DateTimeField(null=True, blank=True)
    # unpaid absence (attendance absent / half day + approved unpaid leave) reduces gross pay
    absence_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # salary advance instalment recovered from this payslip (net = gross - deductions - advance)
    advance_deduction = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, blank=True)
    class Meta:
        unique_together = ("company", "payroll_run", "employee")


class HRSettings(TenantScopedModel):
    """Per-company payroll rules. Weekly off days use Python weekday numbers (Mon=0 ... Sun=6)."""
    weekly_off_days = models.JSONField(default=list, blank=True)
    deduct_absence = models.BooleanField(default=True)
    currency_note = models.CharField(max_length=80, blank=True)
    # advanced features switched on by the owner (see apps.employees.advanced.EXTRAS); all off by default
    extras = models.JSONField(default=list, blank=True)
    # WPS (Qatar Wage Protection System) salary file
    wps_employer_eid = models.CharField(max_length=20, blank=True)
    wps_payer_eid = models.CharField(max_length=20, blank=True)
    wps_payer_qid = models.CharField(max_length=20, blank=True)
    wps_payer_bank = models.CharField(max_length=10, blank=True)
    wps_payer_iban = models.CharField(max_length=34, blank=True)
    # end of service and vacation rules
    gratuity_days_per_year = models.DecimalField(max_digits=5, decimal_places=2, default=21)
    vacation_days_per_year = models.DecimalField(max_digits=5, decimal_places=2, default=21)
    ticket_every_months = models.PositiveSmallIntegerField(default=24)

    GULF = {"qatar", "united arab emirates", "uae", "saudi arabia", "kuwait", "bahrain", "oman"}

    class Meta:
        unique_together = ("company",)

    @classmethod
    def load(cls, company):
        obj = cls.objects.for_company(company).first()
        if obj is None:
            country = (company.country or "").strip().lower()
            off = [4] if country in cls.GULF else [6] if country == "india" else [5, 6]
            obj = cls.objects.create(company=company, weekly_off_days=off)
        return obj


class SalaryAdvance(TenantScopedModel):
    """Money paid to a staff member ahead of salary, recovered from payslips in instalments."""
    METHODS = [("cash", "Cash"), ("bank", "Bank")]
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="advances")
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    monthly_deduction = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS, default="cash")
    reason = models.CharField(max_length=255, blank=True)
    given_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def recovered(self):
        from decimal import Decimal
        return sum((r.amount for r in self.recoveries.all()), Decimal("0"))

    @property
    def outstanding(self):
        return self.amount - self.recovered


class AdvanceRecovery(TenantScopedModel):
    """One repayment of an advance: from a posted payslip, or paid back in cash/bank."""
    SOURCES = [("payroll", "Salary deduction"), ("cash", "Paid back in cash"), ("bank", "Paid back by bank")]
    advance = models.ForeignKey(SalaryAdvance, on_delete=models.CASCADE, related_name="recoveries")
    payroll_line = models.ForeignKey(PayrollLine, null=True, blank=True, on_delete=models.CASCADE, related_name="advance_recoveries")
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    source = models.CharField(max_length=10, choices=SOURCES, default="payroll")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class FinalSettlement(TenantScopedModel):
    """End of service: gratuity, unpaid salary, leave pay and ticket, less advances — then paid and recorded."""
    REASONS = [("resigned", "Resigned"), ("terminated", "Terminated"), ("contract_end", "Contract ended"),
               ("other", "Other")]
    STATUS = [("draft", "Draft"), ("paid", "Paid")]
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="settlements")
    last_day = models.DateField()
    reason = models.CharField(max_length=15, choices=REASONS, default="resigned")
    years = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gratuity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    salary_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    leave_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    leave_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ticket_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other_additions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    advance_deduction = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    method = models.CharField(max_length=10, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Vacation(TenantScopedModel):
    """Annual vacation (home leave) with the air ticket: planned → on vacation → back."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="vacations")
    start_date = models.DateField()
    end_date = models.DateField(help_text="Expected back at work.")
    returned_on = models.DateField(null=True, blank=True)
    ticket_given = models.BooleanField(default=False)
    ticket_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1


class Camp(TenantScopedModel):
    """Staff accommodation (labour camp / flat) and what it costs a month."""
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    monthly_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                       help_text="Rent, electricity, water… for the whole camp a month.")
    food_per_head = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_per_head = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
