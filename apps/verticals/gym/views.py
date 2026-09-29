from rest_framework import viewsets, permissions
from rest_framework.response import Response

from .models import MembershipPlan, GymMember, Attendance
from .serializers import (
    MembershipPlanSerializer, CreateMembershipPlanSerializer,
    GymMemberSerializer, EnrollMemberSerializer, AttendanceSerializer,
)
from .services import create_membership_plan, enroll_member


def _require_gym_module(request):
    """
    Explicit CompanyModule check in the view layer — the URL is wired in
    regardless (Phase 0 Section 8), but every gym endpoint must still check
    the module is active for this company before returning data.
    """
    return request.company.active_modules().filter(code="gym").exists()


class MembershipPlanViewSet(viewsets.ModelViewSet):
    """Creation goes through gym.services.create_membership_plan so every plan
    gets its linked service Product atomically — never a bare model write."""
    serializer_class = MembershipPlanSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_gym_module(self.request):
            return MembershipPlan.objects.none()
        return MembershipPlan.objects.for_company(self.request.company)

    def create(self, request, *args, **kwargs):
        serializer = CreateMembershipPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = create_membership_plan(company=request.company, **serializer.validated_data)
        return Response(MembershipPlanSerializer(plan).data, status=201)


class GymMemberViewSet(viewsets.ModelViewSet):
    """
    Creation goes through gym.services.enroll_member(), which invoices the
    member for the plan's price before the GymMember row is created — a
    member is never active without a real invoice behind it.
    """
    serializer_class = GymMemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_gym_module(self.request):
            return GymMember.objects.none()
        return GymMember.objects.for_company(self.request.company).select_related("customer", "membership_plan")

    def create(self, request, *args, **kwargs):
        serializer = EnrollMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # IDOR guard, same pattern as apps.sales/apps.purchases views — a client-supplied
        # id only proves the row exists somewhere, not that it belongs to this tenant.
        for obj in (data["customer"], data["membership_plan"], data["warehouse"]):
            if obj.company_id != request.company.id:
                return Response({"detail": "Invalid customer, plan, or warehouse for this company."}, status=400)

        member = enroll_member(
            company=request.company, user=request.user, customer=data["customer"],
            membership_plan=data["membership_plan"], join_date=data["join_date"], warehouse=data["warehouse"],
        )
        return Response(GymMemberSerializer(member).data, status=201)


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_gym_module(self.request):
            return Attendance.objects.none()
        return Attendance.objects.for_company(self.request.company).order_by("-check_in")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)
