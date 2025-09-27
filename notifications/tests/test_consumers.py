"""Unit tests for the notification websocket consumer."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace


# Django Channels is not installed in the execution environment used for the
# exercises, so we provide a lightweight stub exposing the attributes used by
# the consumer.  The real implementation is imported transparently when the
# package is available.
if "channels" not in sys.modules:  # pragma: no cover - import-time guard
    channels = types.ModuleType("channels")
    generic = types.ModuleType("channels.generic")
    websocket = types.ModuleType("channels.generic.websocket")

    class _StubAsyncJsonWebsocketConsumer:  # pragma: no cover - helper stub
        """Minimal async websocket base class used by the tests."""

        def __init__(self):
            self.scope = {}
            self.channel_layer = None
            self.channel_name = "test-channel"
            self.accepted = False
            self.closed_code = None
            self.sent_messages = []
            self.disconnected_code = None

        async def accept(self):
            self.accepted = True

        async def close(self, code: int = 1000):
            self.closed_code = code

        async def send_json(self, content):
            self.sent_messages.append(content)

        async def disconnect(self, code):
            self.disconnected_code = code

    websocket.AsyncJsonWebsocketConsumer = _StubAsyncJsonWebsocketConsumer
    generic.websocket = websocket
    channels.generic = generic

    sys.modules["channels"] = channels
    sys.modules["channels.generic"] = generic
    sys.modules["channels.generic.websocket"] = websocket


from notifications.consumers import NotificationConsumer


class DummyChannelLayer:
    """Collect channel-layer actions for assertions."""

    def __init__(self):
        self.add_calls: list[tuple[str, str]] = []
        self.discard_calls: list[tuple[str, str]] = []

    async def group_add(self, group: str, channel: str):
        self.add_calls.append((group, channel))

    async def group_discard(self, group: str, channel: str):
        self.discard_calls.append((group, channel))


def _run(coro):
    """Execute the given coroutine and return its result."""

    return asyncio.run(coro)


def test_connect_rejects_anonymous_user():
    consumer = NotificationConsumer()
    consumer.scope = {"user": SimpleNamespace(is_authenticated=False)}
    consumer.channel_layer = DummyChannelLayer()

    _run(consumer.connect())

    assert getattr(consumer, "group_name", None) is None
    assert consumer.channel_layer.add_calls == []
    assert consumer.closed_code == 4401


def test_connect_authenticated_user_joins_group_and_accepts():
    consumer = NotificationConsumer()
    user = SimpleNamespace(id=42, is_authenticated=True)
    consumer.scope = {"user": user}
    consumer.channel_layer = DummyChannelLayer()

    _run(consumer.connect())

    assert consumer.group_name == "user_42"
    assert consumer.channel_layer.add_calls == [
        ("user_42", consumer.channel_name)
    ]
    assert consumer.accepted is True
    assert consumer.closed_code is None


def test_disconnect_removes_group_and_calls_super():
    consumer = NotificationConsumer()
    user = SimpleNamespace(id=7, is_authenticated=True)
    consumer.scope = {"user": user}
    consumer.channel_layer = DummyChannelLayer()

    _run(consumer.connect())
    _run(consumer.disconnect(3000))

    assert consumer.channel_layer.discard_calls == [
        ("user_7", consumer.channel_name)
    ]
    assert consumer.disconnected_code == 3000


def test_disconnect_without_group_name_skips_channel_layer_cleanup():
    consumer = NotificationConsumer()
    consumer.channel_layer = DummyChannelLayer()

    _run(consumer.disconnect(1001))

    assert consumer.channel_layer.discard_calls == []
    assert consumer.disconnected_code == 1001


def test_notification_created_sends_structured_payload():
    consumer = NotificationConsumer()

    _run(
        consumer.notification_created(
            {"payload": {"id": "notif-1", "detail": "hello"}}
        )
    )

    assert consumer.sent_messages == [
        {
            "event": "notification.created",
            "notification": {"id": "notif-1", "detail": "hello"},
        }
    ]


def test_notification_updated_sends_structured_payload():
    consumer = NotificationConsumer()

    _run(
        consumer.notification_updated(
            {"payload": {"id": "notif-2", "read": True}}
        )
    )

    assert consumer.sent_messages == [
        {
            "event": "notification.updated",
            "notification": {"id": "notif-2", "read": True},
        }
    ]
