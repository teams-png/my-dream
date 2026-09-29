from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Warehouse
from .models import MembershipPlan, GymMember, Attendance


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = ["id", "name", "duration_days", "price", "is_active", "product"]
        read_only_fields = ["id", "product"]


class CreateMembershipPlanSerializer(serializers.Serializer):
    """Input for MembershipPlanViewSet.create — goes through gym.services.create_membership_plan
    so the linked service Product is always created alongside the plan."""
    name = serializers.CharField(max_length=100)
    duration_days = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class GymMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = GymMember
        fields = ["id", "customer", "membership_plan", "join_date", "membership_start", "membership_end", "status"]
        read_only_fields = ["id", "membership_start", "membership_end", "status"]


class EnrollMemberSerializer(serializers.Serializer):
    """Input for GymMemberViewSet.create — goes through gym.services.enroll_member,
    which invoices the plan's price before the member is marked active."""
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    membership_plan = serializers.PrimaryKeyRelatedField(queryset=MembershipPlan.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    join_date = serializers.DateField()


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ["id", "member", "check_in", "check_out"]
        read_only_fields = ["id"]
