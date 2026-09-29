from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, JournalEntryViewSet, TrialBalanceView, FiscalYearViewSet

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("fiscal-years", FiscalYearViewSet, basename="fiscal-year")

urlpatterns = router.urls + [
    path("reports/trial-balance/", TrialBalanceView.as_view(), name="trial-balance"),
]
