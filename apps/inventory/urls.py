from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ProductCategoryViewSet, BrandViewSet, UnitViewSet,
    WarehouseViewSet, ProductViewSet, StockMovementViewSet,
    ProductBatchViewSet, ProductSerialViewSet, StockCountViewSet,
    StockTransferView, StockAdjustmentView,
)

router = DefaultRouter()
router.register("categories", ProductCategoryViewSet, basename="product-category")
router.register("brands", BrandViewSet, basename="brand")
router.register("units", UnitViewSet, basename="unit")
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("products", ProductViewSet, basename="product")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("batches", ProductBatchViewSet, basename="product-batch")
router.register("serials", ProductSerialViewSet, basename="product-serial")
router.register("stock-counts", StockCountViewSet, basename="stock-count")

urlpatterns = router.urls + [
    path("stock-transfer/", StockTransferView.as_view(), name="stock-transfer"),
    path("stock-adjustment/", StockAdjustmentView.as_view(), name="stock-adjustment"),
]
