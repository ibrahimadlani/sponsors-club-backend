"""Business-logic services for the organisations app.

Encapsulates audit logging and email notification for the invitation
lifecycle so that views and serializers stay thin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.http import HttpRequest
from django.template.loader import render_to_string

if TYPE_CHECKING:
    from .models import InvitationAuditLog, OrganisationInvite

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IP extraction
# ---------------------------------------------------------------------------


def get_client_ip(request: HttpRequest) -> str | None:
    """Extract the real client IP, honouring reverse-proxy headers.

    The ``X-Forwarded-For`` header is a comma-separated list where the
    left-most entry is the original client address.  We trust it here
    because the API sits behind a controlled reverse proxy (Nginx/Traefik).

    Args:
        request: The Django HTTP request object.

    Returns:
        The client IP string, or ``None`` when it cannot be determined.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def log_invitation_action(
    invite: "OrganisationInvite",
    action: str,
    *,
    request: HttpRequest | None = None,
    actor=None,
) -> "InvitationAuditLog":
    """Persist an immutable audit log entry for an invitation event.

    Args:
        invite: The invitation being acted upon.
        action: One of ``InvitationAuditLog.Action`` values
            (``"CREATED"``, ``"ACCEPTED"``, ``"REVOKED"``, ``"EXPIRED"``).
        request: Optional HTTP request used to extract IP and User-Agent.
            When supplied, the authenticated user is also used as actor if
            no explicit actor is provided.
        actor: Optional user instance.  Defaults to ``request.user`` when
            the request is authenticated.

    Returns:
        The newly created ``InvitationAuditLog`` record.
    """
    from .models import InvitationAuditLog

    ip_address: str | None = None
    user_agent: str = ""

    if request is not None:
        ip_address = get_client_ip(request)
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]
        if actor is None and hasattr(request, "user") and request.user.is_authenticated:
            actor = request.user

    return InvitationAuditLog.objects.create(
        invite=invite,
        action=action,
        actor=actor,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# ---------------------------------------------------------------------------
# Email notifications
# ---------------------------------------------------------------------------


def send_invitation_created_email(
    invite: "OrganisationInvite",
    recipient_email: str,
) -> None:
    """Send an invitation email to the intended recipient.

    Failure is logged but does **not** raise an exception so that the API
    response is never blocked by an email delivery issue.

    Args:
        invite: The newly created invitation.
        recipient_email: Email address to send the invitation to.
    """
    from core.emails import EmailDeliveryError, EmailMessage, send_email

    organisation = invite.organisation
    context = {
        "organisation_name": organisation.name,
        "invite_code": invite.code,
        "expires_at": invite.expires_at,
        "inviter_name": (
            f"{invite.created_by.user.first_name} {invite.created_by.user.last_name}".strip()
            or invite.created_by.user.email
        ),
    }

    subject = f"Invitation à rejoindre {organisation.name} sur Sponsors Club"
    text_body = render_to_string("emails/organisations/invitation.txt", context)
    html_body = render_to_string("emails/organisations/invitation.html", context)

    message = EmailMessage(
        subject=subject,
        to_addresses=[recipient_email],
        text_body=text_body,
        html_body=html_body,
        tags=[("template", "invitation-created")],
    )

    try:
        send_email(message)
    except EmailDeliveryError:
        logger.warning(
            "Failed to send invitation email for invite %s to %s",
            invite.code,
            recipient_email,
            exc_info=True,
        )


def send_invitation_accepted_email(
    invite: "OrganisationInvite",
    new_member_email: str,
) -> None:
    """Notify the organisation owner that their invitation was accepted.

    Failure is logged but does **not** raise an exception.

    Args:
        invite: The accepted invitation (``is_used`` is already ``True``).
        new_member_email: Email address of the user who joined.
    """
    from core.emails import EmailDeliveryError, EmailMessage, send_email

    owner_email = invite.created_by.user.email
    organisation = invite.organisation
    context = {
        "organisation_name": organisation.name,
        "new_member_email": new_member_email,
        "invite_code": invite.code,
    }

    subject = f"Nouveau membre dans {organisation.name}"
    text_body = render_to_string(
        "emails/organisations/invitation_accepted.txt", context
    )
    html_body = render_to_string(
        "emails/organisations/invitation_accepted.html", context
    )

    message = EmailMessage(
        subject=subject,
        to_addresses=[owner_email],
        text_body=text_body,
        html_body=html_body,
        tags=[("template", "invitation-accepted")],
    )

    try:
        send_email(message)
    except EmailDeliveryError:
        logger.warning(
            "Failed to send invite-accepted email for invite %s to owner %s",
            invite.code,
            owner_email,
            exc_info=True,
        )
