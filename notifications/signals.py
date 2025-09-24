"""Signal handlers for the notifications app."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .emails import send_notification_email
from .models import Notification

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def trigger_notification_email(sender, instance: Notification, created: bool, **kwargs):
    """Send an email whenever a notification is created."""

    if not created:
        return
    try:
        send_notification_email(instance)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unhandled error while sending notification email")
