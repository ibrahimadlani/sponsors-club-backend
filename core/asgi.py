"""ASGI entrypoint wiring HTTP and websocket protocols."""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from messaging.middleware import JWTAuthMiddlewareStack  # noqa: E402
from messaging.routing import websocket_urlpatterns  # noqa: E402

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
