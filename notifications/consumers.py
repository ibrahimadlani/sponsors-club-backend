"""WebSocket consumers pushing notification updates."""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Stream notification changes to authenticated users."""

    group_name: str

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):  # type: ignore[override]
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await super().disconnect(code)

    async def notification_created(self, event):
        await self.send_json(
            {"event": "notification.created", "notification": event["payload"]}
        )

    async def notification_updated(self, event):
        await self.send_json(
            {"event": "notification.updated", "notification": event["payload"]}
        )
