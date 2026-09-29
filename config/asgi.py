import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from apps.verticals.restaurant.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
