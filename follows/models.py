"""Database models for tracking collaborator follows of athletes."""

import uuid

from django.db import models

from athletes.models import Athlete
from organisations.models import Collaborator


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamp metadata."""


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django model configuration metadata."""

        abstract = True


class Follow(BaseModel):
    """Link a collaborator to an athlete they wish to track."""


    collaborator = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        related_name='follows',
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name='follows',
    )
    notify_news = models.BooleanField(default=True)
    notify_stats = models.BooleanField(default=True)
    notify_contracts = models.BooleanField(default=True)

    class Meta:
        """Django model configuration metadata."""

        constraints = [
            models.UniqueConstraint(
                fields=('collaborator', 'athlete'),
                name='unique_follow_collaborator_athlete',
            ),
        ]
        indexes = [
            models.Index(
                fields=('athlete', 'collaborator'),
                name='follow_ath_collab_idx',
            ),
            models.Index(fields=('athlete',), name='follow_athlete_idx'),
        ]

    def __str__(self):
        return f"{self.collaborator} -> {self.athlete}"
