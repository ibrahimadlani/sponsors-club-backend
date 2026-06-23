"""Authentication helpers for ASGI middleware stacks."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthMiddleware:
    """Populate the connection scope user from a JWT when provided."""

    def __init__(self, inner: Callable):
        self.inner = inner
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope: Dict, receive, send):  # type: ignore[override]
        token = self._extract_token(scope)
        if token:
            user = await self._get_user(token)
            if user is not None:
                scope = dict(scope)
                scope["user"] = user
        return await self.inner(scope, receive, send)

    def _extract_token(self, scope: Dict) -> Optional[str]:
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization")
        if authorization:
            try:
                scheme, token = authorization.decode().split(" ", 1)
            except ValueError:
                token = ""
            else:
                if scheme.lower() == "bearer":
                    return token.strip()
        query_string = scope.get("query_string", b"").decode()
        if query_string:
            params = parse_qs(query_string)
            token_values = params.get("token")
            if token_values:
                return token_values[0]
        return None

    @database_sync_to_async
    def _get_user(self, token: str):
        try:
            validated = self.jwt_auth.get_validated_token(token)
            user = self.jwt_auth.get_user(validated)
            return user if user.is_authenticated else AnonymousUser()
        except (
            Exception
        ):  # pragma: no cover - invalid token simply yields anonymous access
            return None


def JWTAuthMiddlewareStack(inner: Callable):
    """Combine Django's auth stack with optional JWT support."""

    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
