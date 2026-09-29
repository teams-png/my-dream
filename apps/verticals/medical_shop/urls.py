from rest_framework.routers import DefaultRouter
from .views import MedicineBatchViewSet, DispenseRecordViewSet

router = DefaultRouter()
router.register("batches", MedicineBatchViewSet, basename="medicine-batch")
router.register("dispense-records", DispenseRecordViewSet, basename="medicine-dispense-record")

urlpatterns = router.urls
