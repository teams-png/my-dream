from rest_framework.routers import DefaultRouter
from .views import VehicleViewSet, WashPackageViewSet, WashOrderViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle-wash-vehicle")
router.register("packages", WashPackageViewSet, basename="vehicle-wash-package")
router.register("orders", WashOrderViewSet, basename="vehicle-wash-order")

urlpatterns = router.urls
