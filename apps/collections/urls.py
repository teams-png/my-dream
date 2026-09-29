from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AgeingBucketViewSet, CollectionNoteViewSet, ARAgeingView, ARAgeingDetailView,
    APAgeingView, APAgeingDetailView, CustomerCreditStatusView,
)

router = DefaultRouter()
router.register("ageing-buckets", AgeingBucketViewSet, basename="ageing-bucket")
router.register("notes", CollectionNoteViewSet, basename="collection-note")

urlpatterns = router.urls + [
    path("ar-ageing/summary/", ARAgeingView.as_view(), name="ar-ageing-summary"),
    path("ar-ageing/detail/", ARAgeingDetailView.as_view(), name="ar-ageing-detail"),
    path("ap-ageing/summary/", APAgeingView.as_view(), name="ap-ageing-summary"),
    path("ap-ageing/detail/", APAgeingDetailView.as_view(), name="ap-ageing-detail"),
    path("customers/<int:customer_id>/credit-status/", CustomerCreditStatusView.as_view(), name="customer-credit-status"),
]
