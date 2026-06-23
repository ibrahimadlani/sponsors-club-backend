"""Signal handlers for the notifications app."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from .emails import send_notification_email
from .models import Notification
from .serializers import NotificationSerializer

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

    channel_layer = get_channel_layer()
    if channel_layer:
        payload = NotificationSerializer(instance).data
        async_to_sync(channel_layer.group_send)(
            f"user_{instance.user_id}",
            {"type": "notification_created", "payload": payload},
        )
