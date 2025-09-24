"""WebSocket consumers handling thread events."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from .models import Thread


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    """Broadcast new messages and read receipts to thread participants."""

    thread_group_name: str

    async def connect(self):
        user = self.scope.get("user")
        thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        thread = await self._get_thread_for_user(thread_id, user.id)
        if not thread:
            await self.close(code=4403)
            return
        self.thread_group_name = f"thread_{thread.id}"
        await self.channel_layer.group_add(self.thread_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):  # type: ignore[override]
        if hasattr(self, "thread_group_name"):
            await self.channel_layer.group_discard(
                self.thread_group_name, self.channel_name
            )
        await super().disconnect(code)

    async def message_created(self, event):
        await self.send_json({"event": "message.created", "message": event["payload"]})

    async def message_read(self, event):
        await self.send_json({"event": "message.read", "message": event["payload"]})

    @database_sync_to_async
    def _get_thread_for_user(self, thread_id: str, user_id: int):
        return (
            Thread.objects.filter(id=thread_id)
            .filter(Q(collaborator__user_id=user_id) | Q(agent__user_id=user_id))
            .first()
        )
