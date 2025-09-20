"""WebSocket consumers and authentication middleware for messaging."""

from __future__ import annotations

from typing import Any

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import Message, Thread
from .serializers import MessageSerializer


class JWTAuthMiddleware(BaseMiddleware):
    """Authenticate WebSocket connections using SimpleJWT tokens."""

    def __init__(self, inner):
        super().__init__(inner)
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope: dict[str, Any], receive, send):
        """Attach the authenticated user to the connection scope."""

        close_old_connections()
        scope["user"] = await self._authenticate(scope)
        return await super().__call__(scope, receive, send)

    async def _authenticate(self, scope: dict[str, Any]):
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization")
        if not auth_header:
            return AnonymousUser()
        prefix, _, token = auth_header.partition(b" ")
        if prefix.lower() != b"bearer" or not token:
            return AnonymousUser()
        raw_token = token.decode()
        try:
            validated = self.jwt_auth.get_validated_token(raw_token)
            user = await database_sync_to_async(self.jwt_auth.get_user)(validated)
            return user
        except (InvalidToken, TokenError):
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):  # noqa: N802 - stack helper mirrors Channels naming convention
    """Return an AuthMiddlewareStack that also supports JWT authentication."""

    return JWTAuthMiddleware(AuthMiddlewareStack(inner))


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    """Handle real-time messaging for a thread."""

    thread: Thread | None = None

    async def connect(self) -> None:
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4003)
            return

        thread_id = self.scope["url_route"]["kwargs"].get("thread_id")
        thread = await self._load_thread(thread_id, user.id)
        if not thread:
            await self.close(code=4003)
            return

        self.thread = thread
        self.group_name = f"thread_{thread.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await super().disconnect(close_code)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        if not self.thread:
            await self.close(code=4003)
            return

        message_text = (content.get("content") or "").strip()
        if not message_text:
            await self.send_json({"error": "Message content is required."})
            return

        message = await self._create_message(message_text)
        payload = await self._serialize_message(message)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "message.created", "payload": payload},
        )

    async def message_created(self, event: dict[str, Any]) -> None:
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _load_thread(self, thread_id, user_id):
        try:
            thread = Thread.objects.select_related(
                "collaborator__user",
                "agent__user",
            ).get(id=thread_id)
        except Thread.DoesNotExist:
            return None
        if user_id not in {thread.collaborator.user_id, thread.agent.user_id}:
            return None
        return thread

    @database_sync_to_async
    def _create_message(self, content: str) -> Message:
        assert self.thread is not None
        message = Message.objects.create(
            thread=self.thread,
            sender=self.scope["user"],
            content=content,
        )
        Thread.objects.filter(id=self.thread.id).update(last_message_at=message.created_at)
        return Message.objects.select_related("sender").get(id=message.id)

    @database_sync_to_async
    def _serialize_message(self, message: Message) -> dict[str, Any]:
        serializer = MessageSerializer(message)
        return serializer.data
