from django.db import models
from apps.tenants.models import TenantScopedModel


class Project(TenantScopedModel):
    STATUS = [
        ("planning", "Planning"), ("active", "Active"),
        ("on_hold", "On Hold"), ("completed", "Completed"), ("cancelled", "Cancelled"),
    ]

    name = models.CharField(max_length=255)
    client = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="projects",
    )
    site_address = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    contract_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Agreed price with the client — used for project profit, separate from internal cost budget.",
    )
    status = models.CharField(max_length=20, choices=STATUS, default="planning")

    def __str__(self):
        return self.name


class Contractor(TenantScopedModel):
    """
    Kept separate from suppliers.Supplier — a contractor is paid for
    labour/subcontracted work per project, not for goods on account, so
    the two are tracked distinctly even though both could theoretically
    share a ledger payable account (Phase 1 Section 12).
    """
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    specialty = models.CharField(max_length=100, blank=True)  # "electrical", "plumbing", ...
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ProjectAssignment(TenantScopedModel):
    """Which Employee (worker) is on which Project — reuses the core Employee model rather than a new Worker table."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="project_assignments")
    role_on_site = models.CharField(max_length=100, blank=True)
    daily_wage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("project", "employee")


class ProjectExpense(TenantScopedModel):
    CATEGORY = [
        ("material", "Material"), ("labour", "Labour"),
        ("contractor", "Contractor"), ("equipment", "Equipment"), ("other", "Other"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=20, choices=CATEGORY)
    contractor = models.ForeignKey(Contractor, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=30, default="cash")
    # Same posting pattern as apps.expenses.services.record_expense — every
    # project expense still hits the ledger, just tagged with a project too.
    journal_entry = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.project.name} - {self.category} - {self.amount}"


class ProjectMilestone(TenantScopedModel):
    STATUS = [("pending", "Pending"), ("in_progress", "In Progress"), ("completed", "Completed"), ("invoiced", "Invoiced")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    completion_percent = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)


class ProjectTask(TenantScopedModel):
    STATUS = [("todo", "To Do"), ("in_progress", "In Progress"), ("blocked", "Blocked"), ("done", "Done")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    milestone = models.ForeignKey(ProjectMilestone, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    title = models.CharField(max_length=200)
    assigned_to = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="todo")
    priority = models.CharField(max_length=20, default="normal")
    description = models.TextField(blank=True)


class ProjectTimesheet(TenantScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="timesheets")
    task = models.ForeignKey(ProjectTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="timesheets")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT)
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)

    @property
    def cost(self):
        return self.hours * self.hourly_rate
