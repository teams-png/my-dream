from rest_framework import serializers

from apps.tenants.models import Company
from apps.subscriptions.models import SubscriptionPlan, Subscription
from apps.subscriptions.serializers import SubscriptionSerializer
from apps.modules.models import Module
from .models import SupportTicket


class TenantSerializer(serializers.ModelSerializer):
    """
    Read view used by the tenant management list/detail — unlike
    tenants.serializers.CompanySerializer (used by the tenant's own Owner),
    `is_active` is writable here since suspend/activate goes through the
    dedicated actions below, not a raw PATCH — kept read-only regardless to
    force every state change through suspend_tenant()/activate_tenant()
    (Phase 0 Section 25) so the audit trail stays meaningful.
    """
    subscription = SubscriptionSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "business_type", "registration_number",
            "email", "phone", "default_currency", "is_active",
            "created_at", "subscription", "member_count",
        ]
        read_only_fields = fields

    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()


class SubscriptionPlanAdminSerializer(serializers.ModelSerializer):
    """Full CRUD serializer — only Super Admin views ever expose this (Phase 0 Section 25)."""
    modules = serializers.PrimaryKeyRelatedField(many=True, queryset=Module.objects.all(), required=False)

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "billing_period", "max_users", "modules", "is_active"]


class ExtendSubscriptionSerializer(serializers.Serializer):
    new_end_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, default="")


class CompanyModuleAssignmentSerializer(serializers.Serializer):
    module_codes = serializers.ListField(child=serializers.SlugField(), allow_empty=True)


class SupportTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            "id", "company", "raised_by", "subject", "message",
            "status", "priority", "assigned_to", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "company", "raised_by", "created_at", "updated_at"]
