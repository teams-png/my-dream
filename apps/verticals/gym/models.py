from django.db import models
from apps.tenants.models import TenantScopedModel


class MembershipPlan(TenantScopedModel):
    name = models.CharField(max_length=100)          # "Monthly", "Quarterly", "Annual"
    duration_days = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True, related_name="gym_membership_plan",
        help_text="The service Product that enroll_member() invoices against — see gym.services.create_membership_plan.",
    )

    def __str__(self):
        return self.name


class GymMember(TenantScopedModel):
    STATUS = [("active", "Active"), ("expired", "Expired"), ("frozen", "Frozen")]

    customer = models.OneToOneField("customers.Customer", on_delete=models.CASCADE, related_name="gym_member")
    membership_plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    join_date = models.DateField()
    membership_start = models.DateField()
    membership_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="active")
    member_no = models.CharField(max_length=30, blank=True)
    trainer = models.ForeignKey("employees.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    goal = models.CharField(max_length=60, blank=True)

    def __str__(self):
        return f"{self.customer.name} ({self.status})"


class Attendance(TenantScopedModel):
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="attendance")
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)


class BodyMeasurement(TenantScopedModel):
    """A member's weight / waist check on a date, so the trainer and member can see progress."""
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="measurements")
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    waist_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def bmi(self):
        if not self.height_cm:
            return None
        metres = float(self.height_cm) / 100
        return round(float(self.weight_kg) / (metres * metres), 1)
