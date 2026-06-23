"""Unit tests for the messaging websocket consumer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync

from messaging.consumers import ThreadConsumer


class DummyChannelLayer:
    """Collect channel layer interactions for assertions."""

    def __init__(self) -> None:
        self.add_calls: list[tuple[str, str]] = []
        self.discard_calls: list[tuple[str, str]] = []

    async def group_add(self, group: str, channel: str) -> None:
        self.add_calls.append((group, channel))

    async def group_discard(self, group: str, channel: str) -> None:
        self.discard_calls.append((group, channel))


def _run(func, *args, **kwargs):
    """Execute the coroutine function and return its result."""

    return async_to_sync(func)(*args, **kwargs)


def _instrument_consumer(consumer: ThreadConsumer) -> DummyChannelLayer:
    """Attach AsyncMock helpers so the consumer can be exercised directly."""

    if not hasattr(consumer, "channel_name"):
        consumer.channel_name = "test-channel"

    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer.send_json = AsyncMock()
    consumer.channel_layer = DummyChannelLayer()
    return consumer.channel_layer


def test_connect_rejects_anonymous_user():
    consumer = ThreadConsumer()
    layer = _instrument_consumer(consumer)
    consumer.scope = {
        "user": SimpleNamespace(is_authenticated=False),
        "url_route": {"kwargs": {"thread_id": "irrelevant"}},
    }

    _run(consumer.connect)

    assert not layer.add_calls
    consumer.close.assert_awaited_once_with(code=4401)
    consumer.accept.assert_not_awaited()


def test_connect_rejects_when_user_not_participant():
    consumer = ThreadConsumer()
    layer = _instrument_consumer(consumer)

    outsider = SimpleNamespace(is_authenticated=True, id=99)
    thread_id = "thread-123"

    consumer.scope = {
        "user": outsider,
        "url_route": {"kwargs": {"thread_id": thread_id}},
    }

    with patch.object(
        ThreadConsumer, "_get_thread_for_user", new=AsyncMock(return_value=None)
    ) as get_thread:
        _run(consumer.connect)

    get_thread.assert_awaited_once_with(thread_id, outsider.id)
    assert not layer.add_calls
    consumer.close.assert_awaited_once_with(code=4403)
    consumer.accept.assert_not_awaited()


def test_connect_accepts_when_user_in_thread():
    consumer = ThreadConsumer()
    layer = _instrument_consumer(consumer)

    agent_user = SimpleNamespace(is_authenticated=True, id=123)
    thread_id = "abc"

    consumer.scope = {
        "user": agent_user,
        "url_route": {"kwargs": {"thread_id": thread_id}},
    }

    thread = SimpleNamespace(id=thread_id)

    with patch.object(
        ThreadConsumer, "_get_thread_for_user", new=AsyncMock(return_value=thread)
    ) as get_thread:
        _run(consumer.connect)

    get_thread.assert_awaited_once_with(thread_id, agent_user.id)
    assert consumer.thread_group_name == f"thread_{thread.id}"
    assert layer.add_calls == [(consumer.thread_group_name, consumer.channel_name)]
    consumer.accept.assert_awaited_once()
    consumer.close.assert_not_awaited()


def test_disconnect_removes_group_and_calls_super():
    consumer = ThreadConsumer()
    layer = _instrument_consumer(consumer)
    agent_user = SimpleNamespace(is_authenticated=True, id=7)
    thread_id = "xyz"
    consumer.scope = {
        "user": agent_user,
        "url_route": {"kwargs": {"thread_id": thread_id}},
    }
    thread = SimpleNamespace(id=thread_id)

    with patch(
        "messaging.consumers.AsyncJsonWebsocketConsumer.disconnect",
        new_callable=AsyncMock,
    ) as super_disconnect:
        with patch.object(
            ThreadConsumer,
            "_get_thread_for_user",
            new=AsyncMock(return_value=thread),
        ):
            _run(consumer.connect)
        _run(consumer.disconnect, 4000)

    assert layer.discard_calls == [(consumer.thread_group_name, consumer.channel_name)]
    super_disconnect.assert_awaited_once_with(4000)


def test_disconnect_without_group_name_skips_cleanup():
    consumer = ThreadConsumer()
    layer = _instrument_consumer(consumer)

    with patch(
        "messaging.consumers.AsyncJsonWebsocketConsumer.disconnect",
        new_callable=AsyncMock,
    ) as super_disconnect:
        _run(consumer.disconnect, 1001)

    assert not layer.discard_calls
    super_disconnect.assert_awaited_once_with(1001)


def test_receive_json_replies_to_ping():
    consumer = ThreadConsumer()
    _instrument_consumer(consumer)

    _run(consumer.receive_json, {"event": "ping"})

    consumer.send_json.assert_awaited_once_with({"event": "pong"})


def test_receive_json_ignores_unknown_events():
    consumer = ThreadConsumer()
    _instrument_consumer(consumer)

    _run(consumer.receive_json, {"event": "ack"})

    consumer.send_json.assert_not_awaited()


def test_message_created_forwards_payload():
    consumer = ThreadConsumer()
    _instrument_consumer(consumer)

    payload = {"payload": {"id": "msg-1"}}

    _run(consumer.message_created, payload)

    consumer.send_json.assert_awaited_once_with(
        {"event": "message.created", "message": payload["payload"]}
    )


def test_message_read_forwards_payload():
    consumer = ThreadConsumer()
    _instrument_consumer(consumer)

    payload = {"payload": {"id": "msg-2", "read": True}}

    _run(consumer.message_read, payload)

    consumer.send_json.assert_awaited_once_with(
        {"event": "message.read", "message": payload["payload"]}
    )
