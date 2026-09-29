from django.urls import path
from .consumers import KitchenConsumer

websocket_urlpatterns = [path("ws/restaurant/kitchen/", KitchenConsumer.as_asgi())]
