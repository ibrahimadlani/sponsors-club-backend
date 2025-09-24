"""Email helpers for delivering notification events."""

from __future__ import annotations

import logging

from django.template.loader import render_to_string

from core.emails import EmailDeliveryError, EmailMessage, send_email

from .models import Notification

logger = logging.getLogger(__name__)


def send_notification_email(notification: Notification) -> None:
    """Send an email representation of the provided notification."""

    user = notification.user
    if not user.email:
        logger.debug(
            "Skipping notification email because recipient %s has no address",
            user,
        )
        return
    if not user.email_verified:
        logger.debug(
            "Skipping notification email for %s because address is unverified",
            user,
        )
        return

    context = {"notification": notification, "user": user}
    text_body = render_to_string("emails/notifications/default.txt", context)
    html_body = render_to_string("emails/notifications/default.html", context)

    message = EmailMessage(
        subject=f"New {notification.get_type_display()} notification",
        to_addresses=[user.email],
        text_body=text_body,
        html_body=html_body,
        tags=(
            ("category", "notification"),
            ("notification_type", notification.type),
        ),
    )
    try:
        send_email(message)
    except EmailDeliveryError:
        logger.exception(
            "Failed to send notification email for %s to %s", notification.id, user.email
        )


__all__ = ["send_notification_email"]
