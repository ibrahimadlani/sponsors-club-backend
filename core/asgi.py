"""ASGI entrypoint configuring HTTP and WebSocket handling."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from messaging.middleware import JWTAuthMiddlewareStack
from messaging.routing import websocket_urlpatterns


django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns,
            )
        ),
    }
)
