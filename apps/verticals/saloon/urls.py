from rest_framework.routers import DefaultRouter
from .views import SaloonServiceViewSet, ServicePackageViewSet, CustomerPackageViewSet, AppointmentViewSet

router = DefaultRouter()
router.register("services", SaloonServiceViewSet, basename="saloon-service")
router.register("packages", ServicePackageViewSet, basename="saloon-package")
router.register("customer-packages", CustomerPackageViewSet, basename="saloon-customer-package")
router.register("appointments", AppointmentViewSet, basename="saloon-appointment")

urlpatterns = router.urls
