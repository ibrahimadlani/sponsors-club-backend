"""ASGI config for the Sponsors Club project.

The ASGI application exposes both the traditional HTTP interface and the
WebSocket endpoints used for real-time messaging and notification delivery.
"""

import os
from importlib import import_module

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

django_asgi_app = get_asgi_application()


def _load_websocket_urlpatterns():
    """Dynamically load websocket URL patterns from installed apps."""

    messaging_routing = import_module("messaging.routing")
    notifications_routing = import_module("notifications.routing")
    return getattr(messaging_routing, "websocket_urlpatterns", []) + getattr(
        notifications_routing, "websocket_urlpatterns", []
    )


from core.auth import JWTAuthMiddlewareStack  # noqa: E402  pylint: disable=wrong-import-position


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(_load_websocket_urlpatterns()))
        ),
    }
)
