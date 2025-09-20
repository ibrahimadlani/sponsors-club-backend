"""Analytics data models for athlete statistics."""

import uuid

from django.db import models

from athletes.models import Athlete


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AthleteStat(BaseModel):
    """Time-series metric captured for an athlete."""

    class Metric(models.TextChoices):
        FOLLOWERS = "followers", "Followers"
        ENGAGEMENT = "engagement", "Engagement"
        RANK = "rank", "Rank"
        CUSTOM = "custom", "Custom"

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="stats",
    )
    metric = models.CharField(max_length=32, choices=Metric.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("athlete", "metric", "date"),
                name="unique_athletestat_per_day",
            ),
        ]
        indexes = [
            models.Index(
                fields=("metric", "date"),
                name="athstat_metric_date_idx",
            ),
            models.Index(
                fields=("athlete", "metric", "date"),
                name="athstat_ath_metric_date_idx",
            ),
        ]
        ordering = ("athlete", "metric", "-date")

    def __str__(self):
        return f"{self.athlete} {self.metric} on {self.date}: {self.value}"
