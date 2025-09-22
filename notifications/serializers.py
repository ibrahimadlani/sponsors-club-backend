"""Serializers for notification resources.

Serializers transform notification model instances into the shape expected by
the API clients and validate partial updates such as read-state toggles.
"""

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
