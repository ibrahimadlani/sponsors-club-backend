"""Data models describing sports and athletes managed on the platform."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from users.models import AgentProfile

# The models in this module are intentionally lightweight and avoid business
# logic so they can be reused across APIs, background tasks, and analytics.


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
    """High-level sport taxonomy grouping multiple disciplines/events."""

    class Category(models.TextChoices):
        TEAM = "TEAM", "Team"
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        MIXED = "MIXED", "Mixed"

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    emoji = models.CharField(max_length=16, blank=True, null=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.INDIVIDUAL
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or uuid.uuid4().hex[:8]
            slug = base_slug
            counter = 1
            while Sport.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)


class SportDiscipline(BaseModel):
    """Specific events or disciplines within a sport (e.g. 100m, Marathon)."""

    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="disciplines",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    is_olympic = models.BooleanField(default=False)

    class Meta:
        unique_together = ("sport", "slug")
        ordering = ("sport__name", "name")

    def __str__(self):
        return f"{self.name} ({self.sport.name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or uuid.uuid4().hex[:8]
            slug = base_slug
            counter = 1
            while SportDiscipline.objects.filter(sport=self.sport, slug=slug).exclude(
                pk=self.pk
            ).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)


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
    followers_count_cached = models.PositiveIntegerField(default=0)
    engagement_rate_cached = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    avatar = models.ImageField(upload_to="athlete_avatars/", blank=True, null=True)
    disciplines = models.ManyToManyField(
        SportDiscipline,
        through="athletes.AthleteDiscipline",
        related_name="athletes",
        blank=True,
    )

    def __str__(self):
        return str(self.full_name)


class AthleteDiscipline(BaseModel):
    """Associative table linking athletes to sport disciplines."""

    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="discipline_links",
    )
    discipline = models.ForeignKey(
        SportDiscipline,
        on_delete=models.CASCADE,
        related_name="athlete_links",
    )

    class Meta:
        unique_together = ("athlete", "discipline")

    def clean(self):
        if self.discipline.sport_id != self.athlete.sport_id:
            raise ValidationError("Discipline must belong to the athlete's sport.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
