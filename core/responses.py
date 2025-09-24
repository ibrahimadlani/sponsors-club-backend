"""Helpers for building consistent API responses."""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def build_error_payload(
    message: str,
    *,
    code: str | None = None,
    details: Any | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Return a standardised payload describing an API error."""

    error: dict[str, Any] = {"message": message}
    if code:
        error["code"] = code
    if details is not None:
        error["details"] = details
    if context:
        error.update(context)

    payload: dict[str, Any] = {"success": False, "error": error, "detail": message}
    if code:
        payload["code"] = code
    if details is not None:
        payload["details"] = details
    if context:
        payload.update(context)
    return payload


def error_response(
    message: str,
    status_code: int,
    *,
    code: str | None = None,
    details: Any | None = None,
    **context: Any,
) -> Response:
    """Return a :class:`~rest_framework.response.Response` with error payload."""

    return Response(
        build_error_payload(message, code=code, details=details, **context),
        status=status_code,
    )

