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

    def __str__(self):
        return self.name


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
    STATUS = [("present", "Present"), ("absent", "Absent"), ("leave", "Leave"), ("holiday", "Holiday")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
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
    class Meta:
        unique_together = ("company", "payroll_run", "employee")
