"""Websocket consumers for real-time messaging updates."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Message, Thread
from .serializers import MessageSerializer


class ThreadConsumer(AsyncWebsocketConsumer):
    """Stream messages for a thread to connected participants."""

    group_name: str
    thread_id: str

    async def connect(self) -> None:
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        try:
            raw_thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
            self.thread_id = str(UUID(str(raw_thread_id)))
        except (KeyError, ValueError):
            await self.close(code=4000)
            return
        thread = await self._get_thread(self.thread_id)
        if thread is None or not await self._user_in_thread(thread, user.id):
            await self.close(code=4403)
            return
        self.group_name = f"thread_{self.thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:  # noqa: D401
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(
        self, text_data: str | None = None, bytes_data: bytes | None = None
    ) -> None:
        del bytes_data
        if text_data is None:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_json({"error": "Invalid JSON payload."})
            return
        content = (payload.get("content") or "").strip()
        if not content:
            await self._send_json({"error": "Message content is required."})
            return
        message_payload = await self._create_and_serialize_message(content)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "thread.message", "message": message_payload},
        )

    async def thread_message(self, event: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(event["message"]))

    async def _send_json(self, payload: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(payload))

    @database_sync_to_async
    def _get_thread(self, thread_id: str) -> Thread | None:
        return (
            Thread.objects.select_related(
                "collaborator__user",
                "agent__user",
            )
            .filter(id=thread_id)
            .first()
        )

    @database_sync_to_async
    def _user_in_thread(self, thread: Thread, user_id: Any) -> bool:
        return user_id in {
            getattr(thread.collaborator, "user_id", None),
            getattr(thread.agent, "user_id", None),
        }

    @database_sync_to_async
    def _create_and_serialize_message(self, content: str) -> dict[str, Any]:
        message = Message.objects.create(
            thread_id=self.thread_id,
            sender=self.scope["user"],
            content=content,
        )
        payload = dict(MessageSerializer(message).data)
        for field in ("id", "thread", "sender"):
            if field in payload and payload[field] is not None:
                payload[field] = str(payload[field])
        return payload
