"""Database models for tracking collaborator follows of athletes.

The follow model links collaborators to athletes and stores notification
preferences that influence messaging throughout the product. Inline comments
and Google-style docstrings make those relationships explicit.
"""

import uuid

from django.db import models

from athletes.models import Athlete
from organisations.models import Collaborator


class BaseModel(models.Model):
    """Provide UUID primary keys and timestamp metadata.

    Attributes:
        id: Primary key generated as a UUID so identifiers are hard to guess
            when exposed through the API.
        created_at: Timestamp marking when the record was created.
        updated_at: Timestamp automatically bumped when the record is saved.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django model configuration metadata."""

        abstract = True


class Follow(BaseModel):
    """Represent a collaborator following an athlete.

    Attributes:
        collaborator: Collaborator that owns the relationship. A collaborator
            may belong to an organisation which controls follow limits.
        athlete: Athlete being tracked so downstream services can surface
            relevant updates.
        notify_news: Toggle for whether organisation staff wish to hear about
            general news events.
        notify_stats: Toggle for stats digests.
        notify_contracts: Toggle for contract updates.
    """

    collaborator = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        related_name="follows",
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="follows",
    )
    notify_news = models.BooleanField(default=True)
    notify_stats = models.BooleanField(default=True)
    notify_contracts = models.BooleanField(default=True)

    class Meta:
        """Additional configuration that enforces uniqueness and indexes.

        The unique constraint prevents duplicate follow relationships while
        the indexes keep lookup queries fast when filtering by athlete or
        collaborator.
        """

        constraints = [
            models.UniqueConstraint(
                fields=("collaborator", "athlete"),
                name="unique_follow_collaborator_athlete",
            ),
        ]
        indexes = [
            models.Index(
                fields=("athlete", "collaborator"),
                name="follow_ath_collab_idx",
            ),
            models.Index(fields=("athlete",), name="follow_athlete_idx"),
        ]

    def __str__(self):
        """Return a readable description for debugging and admin displays."""

        return f"{self.collaborator} -> {self.athlete}"
