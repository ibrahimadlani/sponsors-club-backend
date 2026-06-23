"""Email utilities dedicated to the users application."""

from __future__ import annotations

import logging

from django.conf import settings
from django.template.loader import render_to_string

from core.emails import EmailDeliveryError, EmailMessage, send_email

from .models import EmailVerificationToken, User

logger = logging.getLogger(__name__)


def send_email_verification(user: User) -> None:
    """Issue a verification token and dispatch the email via SES."""

    token = EmailVerificationToken.issue_for_user(user)
    verification_url = None
    if settings.EMAIL_VERIFICATION_URL_TEMPLATE:
        verification_url = settings.EMAIL_VERIFICATION_URL_TEMPLATE.format(
            token=token,
            uid=str(user.id),
        )

    context = {
        "user": user,
        "token": token,
        "verification_url": verification_url,
    }
    text_body = render_to_string("emails/users/verification.txt", context)
    html_body = render_to_string("emails/users/verification.html", context)

    message = EmailMessage(
        subject="Verify your Sponsors Club email address",
        to_addresses=[user.email],
        text_body=text_body,
        html_body=html_body,
        tags=(("category", "email-verification"),),
    )
    try:
        send_email(message)
    except EmailDeliveryError:
        logger.exception("Failed to send verification email to %s", user.email)


__all__ = ["send_email_verification"]
