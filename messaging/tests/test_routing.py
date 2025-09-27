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
    # callable in ``lookup_str``. In environments where this metadata is
    # available we can assert on it directly.
    expected_lookup = "messaging.consumers.ThreadConsumer.as_asgi"
    if getattr(pattern, "lookup_str", None):
        assert pattern.lookup_str == expected_lookup
        return

    # Some Django versions omit ``lookup_str`` for callables that are already
    # materialised. Fall back to comparing the resolved callback with a fresh
    # ``as_asgi`` wrapper to make sure the consumer wiring stays intact.
    expected_callback = ThreadConsumer.as_asgi()
    assert pattern.callback is not None
    assert pattern.callback.__module__ == expected_callback.__module__
    assert pattern.callback.__qualname__ == expected_callback.__qualname__
