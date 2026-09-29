from rest_framework.routers import DefaultRouter
from .views import MobileUnitViewSet, MobileRepairJobViewSet, MobileTradeInViewSet

router = DefaultRouter()
router.register("units", MobileUnitViewSet, basename="mobile-unit")
router.register("repairs", MobileRepairJobViewSet, basename="mobile-repair")
router.register("trade-ins", MobileTradeInViewSet, basename="mobile-trade-in")

urlpatterns = router.urls
