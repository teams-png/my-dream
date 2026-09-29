from rest_framework import serializers
from .models import Company, Role, Permission, CompanyMembership, CompanyOnboarding


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "business_type", "registration_number",
            "address", "phone", "email", "default_currency", "is_active",
        ]
        read_only_fields = ["id", "is_active"]


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "label", "module"]
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "is_system_role", "permission_codes"]
        read_only_fields = ["id", "is_system_role", "permission_codes"]

    def get_permission_codes(self, obj):
        return list(obj.permissions.values_list("permission__code", flat=True))


class SetRolePermissionsSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(child=serializers.CharField())


class CompanyMembershipSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)

    class Meta:
        model = CompanyMembership
        fields = ["id", "user", "company", "role", "is_active", "joined_at"]
        read_only_fields = ["id", "company", "joined_at"]


class InviteMemberSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role_id = serializers.IntegerField()


class RegisterCompanySerializer(serializers.Serializer):
    """
    Input for POST /api/tenants/companies/ (Section 4's "create business"
    step). `business_type` is looked up by its slug code (e.g. "gym",
    "textile", "general_retail" — see apps.modules.models.BusinessType and
    seed_platform), not by numeric id, since that's what a registration
    UI would realistically hold (a dropdown of business type codes/names).
    """
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=50)
    business_type = serializers.SlugField()
    registration_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    default_currency = serializers.CharField(max_length=3, required=False)

    def validate_slug(self, value):
        if Company.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A company with this slug already exists.")
        return value

    def validate_business_type(self, value):
        from apps.modules.models import BusinessType
        try:
            return BusinessType.objects.get(code=value)
        except BusinessType.DoesNotExist:
            raise serializers.ValidationError(f"Unknown business type '{value}'.")


class CompanyOnboardingSerializer(serializers.ModelSerializer):
    is_complete = serializers.ReadOnlyField()

    class Meta:
        model = CompanyOnboarding
        exclude = ["company"]
        read_only_fields = ["completed_at", "updated_at", "is_complete"]


class OnboardingStepSerializer(serializers.Serializer):
    step = serializers.ChoiceField(choices=[
        "company_profile", "accounting_setup", "branch_setup", "products_setup",
        "team_setup", "tax_setup", "opening_balances",
    ])
    complete = serializers.BooleanField(default=True)
