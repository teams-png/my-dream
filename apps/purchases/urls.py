from rest_framework.routers import DefaultRouter
from .views import PurchaseViewSet, PurchaseOrderViewSet, GoodsReceiptNoteViewSet

router = DefaultRouter()
router.register("purchases", PurchaseViewSet, basename="purchase")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("goods-receipts", GoodsReceiptNoteViewSet, basename="goods-receipt")

urlpatterns = router.urls
