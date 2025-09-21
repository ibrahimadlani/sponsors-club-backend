"""Custom middleware for Channels authentication."""

from typing import Callable

from channels.auth import AuthMiddlewareStack

ASGIReceiveCallable = Callable[..., object]
ASGISendCallable = Callable[..., object]
ASGIApp = Callable[[dict, ASGIReceiveCallable, ASGISendCallable], object]


def JWTAuthMiddlewareStack(inner: ASGIApp) -> ASGIApp:
    """Return an authentication middleware stack for JWT-secured connections."""
    return AuthMiddlewareStack(inner)
