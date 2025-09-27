"""Tests for the messaging websocket routing configuration."""

from django.urls.resolvers import URLPattern

from messaging.consumers import ThreadConsumer
from messaging.routing import websocket_urlpatterns


def test_messaging_websocket_urlpattern_defined():
    """The websocket routing should expose the thread endpoint."""
    assert len(websocket_urlpatterns) == 1

    pattern = websocket_urlpatterns[0]
    assert isinstance(pattern, URLPattern)
    assert (
        pattern.pattern.regex.pattern
        == r"^ws/messaging/threads/(?P<thread_id>[0-9a-fA-F\-]{36})/$"
    )


def test_messaging_websocket_urlpattern_uses_thread_consumer():
    """The websocket endpoint should use the thread consumer class."""
    pattern = websocket_urlpatterns[0]
    consumer = pattern.callback

    # as_asgi() assigns the originating consumer class to `view_class`.
    assert getattr(consumer, "view_class", None) is ThreadConsumer
