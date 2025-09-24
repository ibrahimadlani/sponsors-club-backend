"""Serializers for notification resources.

Serializers transform notification model instances into the shape expected by
the API clients and validate partial updates such as read-state toggles.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Expose notification details for API responses.

    The serializer is intentionally read-only for the immutable fields to avoid
    accidental edits from the API side.

    Attributes:
        Meta (type): Configuration specifying which fields are exposed and
            which remain read-only.
    """

    class Meta:
        """Serializer configuration."""

        model = Notification
        fields = (
            "id",
            "type",
            "payload",
            "is_read",
            "created_at",
        )
        read_only_fields = ("id", "type", "payload", "created_at")


class NotificationReadSerializer(serializers.ModelSerializer):
    """Allow toggling the read state of a notification.

    This serializer is constrained to the ``is_read`` flag so clients cannot
    overwrite payload data while marking an item as read.

    Attributes:
        Meta (type): Configuration limiting updates to the ``is_read`` field.
    """

    class Meta:
        """Serializer configuration."""

        model = Notification
        fields = ("is_read",)

    def update(self, instance, validated_data):
        instance.is_read = validated_data.get("is_read", instance.is_read)
        instance.save(update_fields=["is_read", "updated_at"])
        channel_layer = get_channel_layer()
        if channel_layer:
            payload = NotificationSerializer(instance).data
            async_to_sync(channel_layer.group_send)(
                f"user_{instance.user_id}",
                {"type": "notification_updated", "payload": payload},
            )
        return instance
