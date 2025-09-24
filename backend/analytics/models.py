"""Analytics data models for social media statistics."""

import uuid
from datetime import date
from typing import Optional

from django.db import models

from athletes.models import Athlete


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SocialPlatform(BaseModel):
    """Social media platform supported by the analytics stack."""

    class Platform(models.TextChoices):
        TIKTOK = "tiktok", "TikTok"
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        YOUTUBE = "youtube", "YouTube"

    name = models.CharField(max_length=32, choices=Platform.choices, unique=True)
    base_url = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - human readable representation
        return self.get_name_display()


class AthleteSocialAccount(BaseModel):
    """Link between an athlete and one of their social media accounts."""

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    platform = models.ForeignKey(
        SocialPlatform,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    username = models.CharField(max_length=255)
    external_id = models.CharField(max_length=255, unique=True)
    access_token = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("athlete", "platform"),
                name="unique_account_per_platform",
            )
        ]
        ordering = ("athlete", "platform__name")

    def __str__(self) -> str:  # pragma: no cover - human readable representation
        return f"{self.athlete.full_name} - {self.platform.get_name_display()}"


class DailyStatsQuerySet(models.QuerySet):
    """Custom queryset helpers for daily stats."""

    def for_range(self, start_date: Optional[date], end_date: Optional[date]):
        qs = self
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        return qs


class DailyStats(BaseModel):
    """Daily aggregated metrics for a social account."""

    account = models.ForeignKey(
        AthleteSocialAccount,
        on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    date = models.DateField()
    followers = models.PositiveIntegerField()
    following = models.PositiveIntegerField(blank=True, null=True)
    posts_count = models.PositiveIntegerField()
    likes = models.PositiveIntegerField()
    comments = models.PositiveIntegerField()
    shares = models.PositiveIntegerField(blank=True, null=True)
    views = models.PositiveIntegerField(blank=True, null=True)
    watch_time = models.FloatField(blank=True, null=True)
    engagement_rate = models.FloatField(editable=False)
    top_post = models.JSONField(blank=True, null=True)

    objects = DailyStatsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "date"),
                name="unique_stats_per_account_day",
            )
        ]
        indexes = [
            models.Index(fields=("account", "date"), name="dailystats_account_date_idx")
        ]
        ordering = ("account", "-date")

    def __str__(self) -> str:  # pragma: no cover - human readable representation
        return f"{self.account} on {self.date}"

    def compute_engagement_rate(self) -> float:
        """Calculate the engagement rate percentage for the stat line."""

        if not self.followers:
            return 0.0
        interactions = self.likes + self.comments
        if self.shares:
            interactions += self.shares
        engagement = (interactions / self.followers) * 100
        return round(float(engagement), 4)

    def save(self, *args, **kwargs):
        self.engagement_rate = self.compute_engagement_rate()
        super().save(*args, **kwargs)
