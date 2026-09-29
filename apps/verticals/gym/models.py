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

    def __str__(self):
        return f"{self.customer.name} ({self.status})"


class Attendance(TenantScopedModel):
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="attendance")
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
