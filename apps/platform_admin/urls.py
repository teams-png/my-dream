from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tenants", views.TenantViewSet, basename="admin-tenant")
router.register("plans", views.SubscriptionPlanAdminViewSet, basename="admin-plan")
router.register("support-tickets", views.SupportTicketAdminViewSet, basename="admin-support-ticket")

urlpatterns = router.urls + [
    path("dashboard/", views.DashboardStatsView.as_view(), name="admin-dashboard"),
    path("audit-log/", views.PlatformAuditLogView.as_view(), name="admin-audit-log"),
]
