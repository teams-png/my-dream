from rest_framework.routers import DefaultRouter
from .views import ProteinBatchViewSet, SaleRecordViewSet

router = DefaultRouter()
router.register("batches", ProteinBatchViewSet, basename="protein-batch")
router.register("sale-records", SaleRecordViewSet, basename="protein-sale-record")

urlpatterns = router.urls
