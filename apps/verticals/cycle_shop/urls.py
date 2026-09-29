from rest_framework.routers import DefaultRouter
from .views import CycleUnitViewSet, ServiceTicketViewSet

router = DefaultRouter()
router.register("units", CycleUnitViewSet, basename="cycle-unit")
router.register("service-tickets", ServiceTicketViewSet, basename="cycle-service-ticket")

urlpatterns = router.urls
