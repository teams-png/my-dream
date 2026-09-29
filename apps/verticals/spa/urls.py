from rest_framework.routers import DefaultRouter
from .views import SpaServiceViewSet, ServicePackageViewSet, CustomerPackageViewSet, AppointmentViewSet

router = DefaultRouter()
router.register("services", SpaServiceViewSet, basename="spa-service")
router.register("packages", ServicePackageViewSet, basename="spa-package")
router.register("customer-packages", CustomerPackageViewSet, basename="spa-customer-package")
router.register("appointments", AppointmentViewSet, basename="spa-appointment")

urlpatterns = router.urls
