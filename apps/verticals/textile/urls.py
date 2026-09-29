from rest_framework.routers import DefaultRouter
from .views import FabricDetailViewSet, MeasurementViewSet, TailoringOrderViewSet

router = DefaultRouter()
router.register("fabric-details", FabricDetailViewSet, basename="textile-fabric-detail")
router.register("measurements", MeasurementViewSet, basename="textile-measurement")
router.register("tailoring-orders", TailoringOrderViewSet, basename="textile-tailoring-order")

urlpatterns = router.urls
