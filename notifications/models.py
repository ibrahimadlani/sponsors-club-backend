"""Notification models that persist user-facing alerts.

The models in this module favour UUID identifiers and timestamp tracking so
that notifications can be referenced across external systems without leaking
database ids.
"""

import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """Abstract base model with UUID primary keys and timestamps.

    Attributes:
        id (models.UUIDField): Unique identifier that avoids predictable ids
            and simplifies sharding if we ever move notifications to another
            store.
        created_at (models.DateTimeField): Timestamp for when the record was
            created.
        updated_at (models.DateTimeField): Timestamp automatically updated on
            each save.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Metadata that keeps the base model abstract."""

        abstract = True


class Notification(BaseModel):
    """Notification entry targeting a user.

    Attributes:
        user (models.ForeignKey): Recipient that should see the message within
            the notification center.
        type (str): Key describing the kind of notification (e.g. payment,
            new message).
        payload (dict): Metadata payload that holds structured details for the
            client application.
        is_read (bool): Flag indicating whether the recipient has acknowledged
            the notification.
    """

    class Type(models.TextChoices):
        """Supported notification categories for the product."""

        NEW_MESSAGE = "NEW_MESSAGE", "New Message"
        CONTRACT_STATUS = "CONTRACT_STATUS", "Contract Status"
        NEW_FOLLOW = "NEW_FOLLOW", "New Follow"
        STAT_UPDATE = "STAT_UPDATE", "Stat Update"
        PAYMENT = "PAYMENT", "Payment"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        """Metadata that optimises querying for notification lists."""

        # Index fields used together when listing notifications by read status
        # for a particular user.
        indexes = [
            models.Index(
                fields=("user", "is_read", "-created_at"),
            ),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        """Return a concise representation of the notification.

        Returns:
            str: Human-readable representation useful for debugging and admin
            listings.
        """

        # Include the recipient to disambiguate notifications of the same
        # type that may exist for multiple users.
        return f"Notification({self.type}) for {self.user}"
