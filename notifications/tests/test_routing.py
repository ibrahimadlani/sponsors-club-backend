"""Tests for the notifications websocket routing configuration."""

from django.urls.resolvers import URLPattern

from notifications.consumers import NotificationConsumer
from notifications.routing import websocket_urlpatterns


def test_notifications_websocket_urlpattern_defined():
    """The websocket routing should expose a single notifications endpoint."""
    assert len(websocket_urlpatterns) == 1

    pattern = websocket_urlpatterns[0]
    assert isinstance(pattern, URLPattern)
    assert pattern.pattern.regex.pattern == r"^ws/notifications/$"


def test_notifications_websocket_urlpattern_uses_notification_consumer():
    """The websocket endpoint should use the notification consumer class."""
    pattern = websocket_urlpatterns[0]
    consumer = pattern.callback

    # as_asgi() assigns the originating consumer class to `view_class`.
    assert getattr(consumer, "view_class", None) is NotificationConsumer
