from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Company
from apps.subscriptions.models import Subscription, SubscriptionPlan
from apps.audit.models import AuditLog
from apps.audit.services import log_action

from . import services
from .models import SupportTicket
from .permissions import IsPlatformAdmin
from .serializers import (
    TenantSerializer, SubscriptionPlanAdminSerializer,
    ExtendSubscriptionSerializer, SupportTicketSerializer,
    CompanyModuleAssignmentSerializer,
)


class DashboardStatsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(services.dashboard_stats())


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read + a small set of explicit control actions — deliberately NOT a
    full ModelViewSet. A tenant's own data is never edited from here; only
    platform-level state (active/suspended, subscription) is (Phase 0
    Section 25).
    """
    serializer_class = TenantSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = Company.objects.all().select_related("subscription", "subscription__plan").order_by("name")

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        company = self.get_object()
        services.suspend_tenant(company)
        log_action(
            company=company, user=request.user, action="suspend_tenant",
            model_name="Company", object_id=company.id,
        )
        return Response(TenantSerializer(company).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        company = self.get_object()
        services.activate_tenant(company)
        log_action(
            company=company, user=request.user, action="activate_tenant",
            model_name="Company", object_id=company.id,
        )
        return Response(TenantSerializer(company).data)

    @action(detail=True, methods=["post"], url_path="extend-subscription")
    def extend_subscription(self, request, pk=None):
        company = self.get_object()
        subscription = getattr(company, "subscription", None)
        if subscription is None:
            return Response({"detail": "Company has no subscription record."}, status=status.HTTP_400_BAD_REQUEST)

        payload = ExtendSubscriptionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        services.extend_subscription(subscription, **payload.validated_data)

        log_action(
            company=company, user=request.user, action="extend_subscription",
            model_name="Subscription", object_id=subscription.id,
            changes={k: str(v) for k, v in payload.validated_data.items()},
        )
        return Response(TenantSerializer(company).data)

    @action(detail=True, methods=["post"], url_path="cancel-subscription")
    def cancel_subscription(self, request, pk=None):
        company = self.get_object()
        subscription = getattr(company, "subscription", None)
        if subscription is None:
            return Response({"detail": "Company has no subscription record."}, status=status.HTTP_400_BAD_REQUEST)

        services.cancel_subscription(subscription)
        log_action(
            company=company, user=request.user, action="cancel_subscription",
            model_name="Subscription", object_id=subscription.id,
        )
        return Response(TenantSerializer(company).data)

    @action(detail=True, methods=["get", "post"], url_path="modules")
    def modules(self, request, pk=None):
        company = self.get_object()
        if request.method == "GET":
            return Response({"modules": list(company.active_modules().values("code", "name", "is_core"))})
        payload = CompanyModuleAssignmentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        from apps.modules.services import set_company_modules
        try:
            enabled = set_company_modules(company=company, module_codes=payload.validated_data["module_codes"])
        except Exception as exc:
            return Response({"detail": str(exc)}, status=400)
        log_action(company=company, user=request.user, action="set_modules", model_name="Company", object_id=company.id,
                   changes={"enabled": sorted(payload.validated_data["module_codes"])})
        return Response({"modules": list(enabled.values("code", "name", "is_core"))})


class SubscriptionPlanAdminViewSet(viewsets.ModelViewSet):
    """Full CRUD — plans are never hardcoded (Phase 0 Section 6); this is the only place they're authored."""
    serializer_class = SubscriptionPlanAdminSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = SubscriptionPlan.objects.all().order_by("name")


class SupportTicketAdminViewSet(viewsets.ModelViewSet):
    """
    Platform-wide ticket queue — every tenant's tickets in one place, unlike
    a tenant-scoped viewset elsewhere that would only show one company's.
    """
    serializer_class = SupportTicketSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = SupportTicket.objects.all().select_related("company", "raised_by", "assigned_to")


class PlatformAuditLogView(APIView):
    """
    Cross-tenant audit trail — the one sanctioned place in the codebase
    that reads AuditLog.objects.all() instead of .for_company(...), since a
    platform admin legitimately needs visibility across every tenant
    (Phase 0 Section 28: "audit logs should not be easily deleted by
    normal users" — this view is also read-only, no delete endpoint).
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        qs = AuditLog.objects.all().select_related("company", "user").order_by("-timestamp")[:200]
        data = [
            {
                "id": a.id, "company": a.company.name, "user": str(a.user) if a.user else None,
                "action": a.action, "model_name": a.model_name, "object_id": a.object_id,
                "timestamp": a.timestamp,
            }
            for a in qs
        ]
        return Response(data)
