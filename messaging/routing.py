"""WebSocket routing configuration for messaging."""

from django.urls import re_path

from .consumers import ThreadConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/messaging/threads/(?P<thread_id>[0-9a-fA-F\-]{36})/$",
        ThreadConsumer.as_asgi(),
    ),
]
