"""Data models describing sports and athletes managed on the platform."""

# pylint: disable=missing-class-docstring,too-few-public-methods

import uuid

from django.db import models

from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Sport(BaseModel):
    """Categorise athletes by sport and discipline."""

    name = models.CharField(max_length=255, unique=True)
    discipline = models.CharField(max_length=255)

    def __str__(self):
        return str(self.name)


class Athlete(BaseModel):
    """Represent an athlete profile managed by an agent or self-represented."""

    sport = models.ForeignKey(
        Sport,
        on_delete=models.PROTECT,
        related_name="athletes",
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name="athletes",
    )
    full_name = models.CharField(max_length=255)
    birth_date = models.DateField()
    nationality = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    is_self_represented = models.BooleanField(default=False)
    followers_count_cached = models.PositiveIntegerField(default=0)
    engagement_rate_cached = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    avatar = models.ImageField(upload_to="athlete_avatars/", blank=True, null=True)

    def __str__(self):
        return str(self.full_name)
