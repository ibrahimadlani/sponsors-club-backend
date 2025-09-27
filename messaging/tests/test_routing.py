"""Tests for the messaging websocket routing configuration."""

import pytest
from django.urls.resolvers import URLPattern

pytest.importorskip("channels")

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

    # When Django builds the URL pattern, it stores the import string for the
    # callable in ``lookup_str``. This lets us assert which consumer class backs
    # the endpoint without relying on ``pattern.callback`` (which may be ``None``
    # when Channels is unavailable in the environment running the tests).
    assert pattern.lookup_str == "messaging.consumers.ThreadConsumer.as_asgi"
