"""Database models for persisting notifications."""

import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    # pylint: disable=too-few-public-methods

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django metadata configuration for abstract base."""

        abstract = True


class Notification(BaseModel):
    """Notification entry targeting a user."""

    # pylint: disable=too-few-public-methods

    class Type(models.TextChoices):
        """Supported notification categories."""

        NEW_MESSAGE = 'NEW_MESSAGE', 'New Message'
        CONTRACT_STATUS = 'CONTRACT_STATUS', 'Contract Status'
        NEW_FOLLOW = 'NEW_FOLLOW', 'New Follow'
        STAT_UPDATE = 'STAT_UPDATE', 'Stat Update'
        PAYMENT = 'PAYMENT', 'Payment'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        """Django metadata configuration for notifications."""

        indexes = [
            models.Index(
                fields=('user', 'is_read', '-created_at'),
            ),
        ]
        ordering = ('-created_at',)

    def __str__(self):
        return f"Notification({self.type}) for {self.user}"
