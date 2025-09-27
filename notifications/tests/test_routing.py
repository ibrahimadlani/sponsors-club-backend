"""Tests for the notifications websocket routing configuration."""

import pytest
from django.urls.resolvers import URLPattern

pytest.importorskip("channels")

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

    # ``lookup_str`` records the dotted import path to the consumer callable.
    # Comparing it lets us verify the endpoint wiring without depending on the
    # Channels runtime being importable in the current environment.
    assert (
        pattern.lookup_str == "notifications.consumers.NotificationConsumer.as_asgi"
    )
