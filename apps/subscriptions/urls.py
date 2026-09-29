from django.urls import path
from .views import MySubscriptionView

urlpatterns = [
    path("me/", MySubscriptionView.as_view(), name="my-subscription"),
]
