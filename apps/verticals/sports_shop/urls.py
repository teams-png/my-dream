from rest_framework.routers import DefaultRouter
from .views import SportsProductDetailViewSet

router = DefaultRouter()
router.register("product-details", SportsProductDetailViewSet, basename="sports-product-detail")

urlpatterns = router.urls
