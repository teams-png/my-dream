from rest_framework.routers import DefaultRouter
from .views import BeautyServiceViewSet, ServicePackageViewSet, CustomerPackageViewSet, AppointmentViewSet

router = DefaultRouter()
router.register("services", BeautyServiceViewSet, basename="beauty-service")
router.register("packages", ServicePackageViewSet, basename="beauty-package")
router.register("customer-packages", CustomerPackageViewSet, basename="beauty-customer-package")
router.register("appointments", AppointmentViewSet, basename="beauty-appointment")

urlpatterns = router.urls
