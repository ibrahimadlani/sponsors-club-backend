"""Serializers for notification resources."""


from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Expose notification details for API responses."""

    class Meta:
        """Serializer configuration."""

        model = Notification
        fields = (
            'id',
            'type',
            'payload',
            'is_read',
            'created_at',
        )
        read_only_fields = ('id', 'type', 'payload', 'created_at')


class NotificationReadSerializer(serializers.ModelSerializer):
    """Allow toggling the read state of a notification."""

    class Meta:
        """Serializer configuration."""

        model = Notification
        fields = ('is_read',)
