"""Unit tests for the notification websocket consumer."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


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
            self.base_send = self._base_send

        async def accept(self):
            self.accepted = True

        async def close(self, code: int = 1000):
            self.closed_code = code

        async def send_json(self, content):
            self.sent_messages.append(content)

        async def _base_send(self, message):
            self.sent_messages.append(message)

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


def _instrument_consumer(consumer: NotificationConsumer) -> None:
    """Attach AsyncMock helpers so the consumer can be exercised directly."""

    if not hasattr(consumer, "channel_name"):
        consumer.channel_name = "test-channel"

    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer.send_json = AsyncMock()
    consumer.channel_layer = DummyChannelLayer()


def test_connect_rejects_anonymous_user():
    consumer = NotificationConsumer()
    _instrument_consumer(consumer)
    consumer.scope = {"user": SimpleNamespace(is_authenticated=False)}

    _run(consumer.connect())

    assert getattr(consumer, "group_name", None) is None
    assert consumer.channel_layer.add_calls == []
    consumer.close.assert_awaited_once_with(code=4401)


def test_connect_authenticated_user_joins_group_and_accepts():
    consumer = NotificationConsumer()
    _instrument_consumer(consumer)
    user = SimpleNamespace(id=42, is_authenticated=True)
    consumer.scope = {"user": user}

    _run(consumer.connect())

    assert consumer.group_name == "user_42"
    assert consumer.channel_layer.add_calls == [("user_42", consumer.channel_name)]
    consumer.accept.assert_awaited_once()
    consumer.close.assert_not_awaited()


def test_disconnect_removes_group_and_calls_super():
    with patch(
        "notifications.consumers.AsyncJsonWebsocketConsumer.disconnect",
        new_callable=AsyncMock,
    ) as super_disconnect:
        consumer = NotificationConsumer()
        _instrument_consumer(consumer)
        user = SimpleNamespace(id=7, is_authenticated=True)
        consumer.scope = {"user": user}

        _run(consumer.connect())
        _run(consumer.disconnect(3000))

        assert consumer.channel_layer.discard_calls == [
            ("user_7", consumer.channel_name)
        ]
        super_disconnect.assert_awaited_once_with(3000)


def test_disconnect_without_group_name_skips_channel_layer_cleanup():
    with patch(
        "notifications.consumers.AsyncJsonWebsocketConsumer.disconnect",
        new_callable=AsyncMock,
    ) as super_disconnect:
        consumer = NotificationConsumer()
        _instrument_consumer(consumer)

        _run(consumer.disconnect(1001))

        assert consumer.channel_layer.discard_calls == []
        super_disconnect.assert_awaited_once_with(1001)


def test_notification_created_sends_structured_payload():
    consumer = NotificationConsumer()
    _instrument_consumer(consumer)

    _run(
        consumer.notification_created({"payload": {"id": "notif-1", "detail": "hello"}})
    )

    consumer.send_json.assert_awaited_once()
    assert consumer.send_json.await_args.args == (
        {
            "event": "notification.created",
            "notification": {"id": "notif-1", "detail": "hello"},
        },
    )


def test_notification_updated_sends_structured_payload():
    consumer = NotificationConsumer()
    _instrument_consumer(consumer)

    _run(consumer.notification_updated({"payload": {"id": "notif-2", "read": True}}))

    consumer.send_json.assert_awaited_once()
    assert consumer.send_json.await_args.args == (
        {
            "event": "notification.updated",
            "notification": {"id": "notif-2", "read": True},
        },
    )
