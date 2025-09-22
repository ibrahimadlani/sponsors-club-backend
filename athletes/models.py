"""Data models describing sports and athletes managed on the platform."""

# The models in this module are intentionally lightweight and avoid business
# logic so they can be reused across APIs, background tasks, and analytics.

import uuid

from django.db import models

from users.models import AgentProfile


class BaseModel(models.Model):
    """Common fields shared by models in the athletes app.

    Attributes:
        id (uuid.UUID): Primary key used to uniquely identify each record.
        created_at (datetime.datetime): Timestamp when the record is created.
        updated_at (datetime.datetime): Timestamp automatically refreshed when
            the record changes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Using UUIDs ensures unique identifiers even when records are synced
    # across multiple services or environments.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Sport(BaseModel):
    """Categorise athletes by sport and discipline.

    Attributes:
        name (str): Public name of the sport (for example "Basketball").
        discipline (str): Sub-discipline or event to help filter athletes.
    """

    name = models.CharField(max_length=255)
    # Discipline provides additional granularity, such as "Track" vs "Field".

    discipline = models.CharField(max_length=255)
    class Meta:
        unique_together = ("name", "discipline")

    def __str__(self):
        return str(self.name)


class Athlete(BaseModel):
    """Represent an athlete profile managed by an agent or self-represented.

    Attributes:
        sport (Sport): Sport category the athlete competes in.
        agent (users.models.AgentProfile): Agent managing the athlete profile.
        full_name (str): Display name that appears across the platform.
        birth_date (datetime.date): Date of birth for compliance checks.
        nationality (str): ISO country code representing the athlete's origin.
        bio (str): Optional free-form biography shown in public listings.
        social_links (dict[str, str]): Mapping of platform names to profile URLs.
        is_self_represented (bool): Indicates whether the athlete manages their
            own relationships rather than working with an agent.
        followers_count_cached (int): Cached follower count from social stats.
        engagement_rate_cached (decimal.Decimal): Cached engagement rate used
            for quick filtering in the UI.
        avatar (django.db.models.fields.files.Field): Profile image stored in
            media storage.
    """

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
