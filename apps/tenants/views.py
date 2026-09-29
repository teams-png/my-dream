from rest_framework import generics, permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .models import Company, Role, Permission, CompanyMembership, CompanyOnboarding
from .permissions import HasCompanyPermission
from .services import invite_member, set_role_permissions, create_company_with_owner, complete_onboarding_step, provision_company_basics
from .serializers import (
    CompanySerializer, RoleSerializer, PermissionSerializer,
    SetRolePermissionsSerializer, CompanyMembershipSerializer, InviteMemberSerializer,
    RegisterCompanySerializer, CompanyOnboardingSerializer, OnboardingStepSerializer,
)


class MyCompaniesView(generics.ListAPIView):
    """All companies the logged-in user belongs to (for the company switcher)."""
    serializer_class = CompanyMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.memberships.select_related("company", "role").filter(is_active=True)


class CompanyRegisterView(APIView):
    """
    POST /api/tenants/companies/ — Section 4's "create business" step.
    Deliberately not gated by HasCompanyPermission: the caller has no
    company yet at this point, only a logged-in user account from
    registration/login. Wraps tenants.services.create_company_with_owner,
    which atomically creates the Company, seeds roles/permissions/modules/
    trial subscription/chart of accounts, and makes the caller Owner.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RegisterCompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        business_type = data.pop("business_type")

        company = create_company_with_owner(
            user=request.user, name=data.pop("name"), slug=data.pop("slug"),
            business_type=business_type, **data,
        )
        request.session["active_company_id"] = company.id
        return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


class ActiveCompanyView(APIView):
    """GET current active company; POST {company_id} to switch (company-switcher, Phase 0 Section 3)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.company:
            return Response({"detail": "No active company."}, status=404)
        return Response(CompanySerializer(request.company).data)

    def post(self, request):
        company_id = request.data.get("company_id")
        membership = request.user.memberships.filter(
            company_id=company_id, is_active=True, company__is_active=True
        ).select_related("company").first()
        if not membership:
            return Response({"detail": "Not a member of that company."}, status=403)
        request.session["active_company_id"] = membership.company_id
        return Response(CompanySerializer(membership.company).data)


class CompanyOnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "tenants.manage_roles"}

    def get(self, request):
        state, _ = CompanyOnboarding.objects.get_or_create(company=request.company)
        return Response(CompanyOnboardingSerializer(state).data)

    def post(self, request):
        payload = OnboardingStepSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if payload.validated_data["step"] == "branch_setup" and payload.validated_data["complete"]:
            provision_company_basics(company=request.company)
        state = complete_onboarding_step(
            company=request.company, step=payload.validated_data["step"], value=payload.validated_data["complete"],
        )
        return Response(CompanyOnboardingSerializer(state).data)


class PermissionListView(generics.ListAPIView):
    """The full permission catalog — used by the Owner's role-editor UI."""
    queryset = Permission.objects.all().order_by("module", "code")
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "tenants.manage_roles"}


class RoleViewSet(viewsets.ModelViewSet):
    """
    Owner can create custom roles and set their permissions
    (Phase 0 Section 6 — "Owner should be able to customize permissions").
    System roles (Owner/Accountant/Staff) are read-only here — see
    tenants.services.set_role_permissions.
    """
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "tenants.manage_roles", "list": "tenants.manage_roles", "retrieve": "tenants.manage_roles"}

    def get_queryset(self):
        return Role.objects.filter(company=self.request.company).order_by("name")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, is_system_role=False)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system_role:
            return Response({"detail": "System roles cannot be deleted."}, status=400)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def set_permissions(self, request, pk=None):
        role = self.get_object()
        serializer = SetRolePermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_role_permissions(role=role, permission_codes=serializer.validated_data["permission_codes"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(RoleSerializer(role).data)


class MembershipViewSet(viewsets.ModelViewSet):
    """Manage who belongs to the active company. Invite enforces the subscription's max_users."""
    serializer_class = CompanyMembershipSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "tenants.manage_members", "list": "tenants.manage_members"}
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        return CompanyMembership.objects.filter(company=self.request.company).select_related("user", "role")

    def create(self, request, *args, **kwargs):
        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.filter(id=data["user_id"]).first()
        role = Role.objects.filter(id=data["role_id"], company=request.company).first()
        if not user or not role:
            return Response({"detail": "Invalid user or role."}, status=400)

        try:
            membership = invite_member(company=request.company, user=user, role=role)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_402_PAYMENT_REQUIRED)

        return Response(CompanyMembershipSerializer(membership).data, status=201)
