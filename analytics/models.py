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
    """Social media platform supported by the analytics stack.

    Attributes:
        name: Slug identifier matching a ``Platform`` choice (e.g., "instagram").
        base_url: Optional root URL used to build profile links.
    """

    class Platform(models.TextChoices):
        """Supported social networks for the analytics integration."""

        TIKTOK = "tiktok", "TikTok"
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        YOUTUBE = "youtube", "YouTube"

    name = models.CharField(max_length=32, choices=Platform.choices, unique=True)
    base_url = models.URLField(blank=True, null=True)

    class Meta:
        """Order platforms alphabetically by name."""

        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover
        """Return the human-readable platform display name."""
        return self.get_name_display()


class AthleteSocialAccount(BaseModel):
    """Link between an athlete and one of their social media accounts.

    Attributes:
        athlete: The athlete who owns this social account.
        platform: The social network (TikTok, Instagram, Facebook, YouTube).
        username: Public handle or username on the platform.
        external_id: Platform-assigned unique identifier; globally unique.
        access_token: OAuth token used to fetch stats; may be null for manual entry.
        is_active: False when the account is disconnected or deauthorised.
    """

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
        """Enforce one account per athlete per platform and order by name."""

        constraints = [
            models.UniqueConstraint(
                fields=("athlete", "platform"),
                name="unique_account_per_platform",
            )
        ]
        ordering = ("athlete", "platform__name")

    def __str__(self) -> str:  # pragma: no cover
        """Return the athlete name and platform display name."""
        return f"{self.athlete.full_name} - {self.platform.get_name_display()}"


class DailyStatsQuerySet(models.QuerySet):
    """Custom queryset helpers for daily stats."""

    def for_range(
        self, start_date: Optional[date], end_date: Optional[date]
    ) -> "DailyStatsQuerySet":
        """Restrict stats to a specific inclusive date window.

        Args:
            start_date: Earliest date to retain, or ``None`` for open ended.
            end_date: Latest date to retain, or ``None`` to include all future values.

        Returns:
            DailyStatsQuerySet: Queryset filtered to the requested bounds.
        """

        qs = self
        if start_date:
            # Apply a lower bound when the consumer provided a start date.
            qs = qs.filter(date__gte=start_date)
        if end_date:
            # Similarly clamp the results to the requested upper bound.
            qs = qs.filter(date__lte=end_date)
        return qs


class DailyStats(BaseModel):
    """Daily aggregated metrics for a social account.

    Attributes:
        account: The social account these stats belong to.
        date: Calendar day for this stat snapshot; unique per account.
        followers: Total follower count at time of capture.
        engagement_rate: Auto-computed percentage of followers who interacted;
            not editable directly — recalculated on every ``save()``.
        top_post: Optional JSON payload describing the best-performing post.
    """

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
        """Enforce uniqueness per account/day and optimise time-series queries."""

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

    def __str__(self) -> str:  # pragma: no cover
        """Return account identifier and date as the string representation."""
        return f"{self.account} on {self.date}"

    def compute_engagement_rate(self) -> float:
        """Calculate the engagement rate percentage for the stat line.

        Returns:
            float: Engagement percentage rounded to four decimal places.
        """

        if not self.followers:
            # Avoid division by zero when the platform did not report followers.
            return 0.0
        interactions = self.likes + self.comments
        if self.shares:
            # Shares are optional but should contribute to total interactions.
            interactions += self.shares
        engagement = (interactions / self.followers) * 100
        return round(float(engagement), 4)

    def save(self, *args, **kwargs):
        """Persist the stat while refreshing derived engagement metrics.

        Args:
            *args: Positional arguments forwarded to :meth:`models.Model.save`.
            **kwargs: Keyword arguments forwarded to :meth:`models.Model.save`.

        Returns:
            None: The method relies on Django's base ``save`` return value.
        """

        # Always recompute engagement to ensure the stored value matches inputs.
        self.engagement_rate = self.compute_engagement_rate()
        super().save(*args, **kwargs)
