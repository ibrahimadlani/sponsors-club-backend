"""Custom Channels authentication middleware supporting JWT tokens."""

from __future__ import annotations

from typing import Any

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

jwt_authentication = JWTAuthentication()


class JWTAuthMiddleware(BaseMiddleware):
    """Resolve the websocket user from a Bearer token if provided."""

    async def __call__(self, scope: dict[str, Any], receive, send):  # type: ignore[override]
        scope = dict(scope)
        scope.setdefault("user", AnonymousUser())
        token = self._get_token_from_scope(scope)
        if token:
            user = await self._authenticate_token(token)
            if user is not None:
                scope["user"] = user
        return await super().__call__(scope, receive, send)

    @staticmethod
    def _get_token_from_scope(scope: dict[str, Any]) -> str | None:
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization")
        if not auth_header:
            return None
        try:
            prefix, token = auth_header.decode().split(" ", 1)
        except ValueError:
            return None
        if prefix.lower() != "bearer" or not token:
            return None
        return token

    @database_sync_to_async
    def _authenticate_token(self, token: str):
        try:
            validated_token = jwt_authentication.get_validated_token(token)
            return jwt_authentication.get_user(validated_token)
        except (InvalidToken, AuthenticationFailed):
            return None


def JWTAuthMiddlewareStack(inner):
    """Apply the JWT middleware on top of Django's auth stack."""

    return JWTAuthMiddleware(AuthMiddlewareStack(inner))


__all__ = ["JWTAuthMiddleware", "JWTAuthMiddlewareStack"]
