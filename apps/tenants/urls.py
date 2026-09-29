from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    MyCompaniesView, ActiveCompanyView, PermissionListView, RoleViewSet,
    MembershipViewSet, CompanyRegisterView, CompanyOnboardingView,
)

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("members", MembershipViewSet, basename="member")

urlpatterns = router.urls + [
    path("companies/", CompanyRegisterView.as_view(), name="company-register"),
    path("my-companies/", MyCompaniesView.as_view(), name="my-companies"),
    path("active-company/", ActiveCompanyView.as_view(), name="active-company"),
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    path("onboarding/", CompanyOnboardingView.as_view(), name="company-onboarding"),
]
