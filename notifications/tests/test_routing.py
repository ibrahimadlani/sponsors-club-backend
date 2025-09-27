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
    expected_lookup = "notifications.consumers.NotificationConsumer"
    if getattr(pattern, "lookup_str", None):
        assert pattern.lookup_str == expected_lookup
        return

    # If the URL resolver skipped populating ``lookup_str`` we fall back to
    # comparing the resolved callable with a freshly materialised ``as_asgi``
    # wrapper. This ensures the route continues to point at the consumer.
    expected_callback = NotificationConsumer.as_asgi()
    assert pattern.callback is not None
    assert pattern.callback.__module__ == expected_callback.__module__
    assert pattern.callback.__qualname__ == expected_callback.__qualname__
