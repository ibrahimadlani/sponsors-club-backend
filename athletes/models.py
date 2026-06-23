"""Data models describing sports and athletes managed on the platform.

Architecture "Sport-Business" : la valeur d'un athlète est calculée à partir
de ses résultats sportifs vérifiés, de sa visibilité physique et des espaces
publicitaires (inventaire) qu'il a réellement à vendre — et non de ses seuls
followers sur les réseaux sociaux.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from users.models import AgentProfile, RepresentativeProfile


class BaseModel(models.Model):
    """Common fields shared by models in the athletes app.

    Attributes:
        id (uuid.UUID): Primary key used to uniquely identify each record.
        created_at (datetime.datetime): Timestamp when the record is created.
        updated_at (datetime.datetime): Timestamp automatically refreshed when
            the record changes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.sport.name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or uuid.uuid4().hex[:8]
            slug = base_slug
            counter = 1
            while (
                SportDiscipline.objects.filter(sport=self.sport, slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
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
        avatar: Profile image stored in media storage.
        club_name (str): Current club the athlete competes with.
        federation_name (str): Governing federation (e.g. Fédération Française de Judo).
        license_number (str): Optional license number for identity verification.
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
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    birth_date = models.DateField()
    nationality = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g., FR, US, GB)",
    )
    country = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text="ISO 3166-1 alpha-2 country code (e.g., FR, US, GB)",
    )
    city = models.CharField(max_length=255, blank=True, default="")
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
    entourage = models.ManyToManyField(
        RepresentativeProfile,
        through="RepresentationMandate",
        related_name="represented_athletes",
        blank=True,
    )

    # --- Institutional identity (legal baseline for insurance & contracts) ---
    club_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Club actuel de l'athlète (affilié à la fédération).",
    )
    federation_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Fédération sportive nationale (ex : Fédération Française de Judo).",
    )
    license_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Numéro de licence fédérale (optionnel, utilisé pour la vérification d'identité sportive).",
    )

    def __str__(self):
        return str(self.full_name)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.full_name) or uuid.uuid4().hex[:8]
            slug = base_slug
            counter = 1
            while Athlete.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def total_physical_reach(self) -> int:
        """Compute the total in-person audience across all future events.

        Exploits the prefetch cache (``upcoming_events``) when available to
        avoid issuing an additional query in list views.

        Returns:
            int: Sum of ``estimated_physical_audience`` for events whose
            ``start_date`` is today or in the future.  Returns 0 when the
            athlete has no scheduled events.
        """
        today = timezone.now().date()
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "upcoming_events" in cache:
            return sum(
                e.estimated_physical_audience
                for e in cache["upcoming_events"]
                if e.start_date >= today
            )
        return (
            self.upcoming_events.filter(start_date__gte=today).aggregate(
                total=models.Sum("estimated_physical_audience")
            )["total"]
            or 0
        )

    @property
    def sponsorship_tier(self) -> str:
        """Return the athlete's commercial tier based on verified achievements.

        The tier is computed dynamically from ``SportingAchievement`` records
        with ``verification_status=VERIFIED``.  Only staff-verified results are
        taken into account so sponsors can trust the label.

        Tier ladder:
            * **Élite Nationale** — at least one NATIONAL or INTERNATIONAL
              verified achievement.
            * **Espoir Régional** — highest verified achievement is REGIONAL.
            * **Héros Local** — only LOCAL achievements, or none yet verified.

        Exploits the prefetch cache (``achievements``) when available.

        Returns:
            str: One of ``"Élite Nationale"``, ``"Espoir Régional"``,
            ``"Héros Local"``.
        """
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "achievements" in cache:
            verified_levels = {
                a.level
                for a in cache["achievements"]
                if a.verification_status
                == SportingAchievement.VerificationStatus.VERIFIED
            }
        else:
            verified_levels = set(
                self.achievements.filter(
                    verification_status=SportingAchievement.VerificationStatus.VERIFIED
                ).values_list("level", flat=True)
            )

        if (
            SportingAchievement.Level.INTERNATIONAL in verified_levels
            or SportingAchievement.Level.NATIONAL in verified_levels
        ):
            return "Élite Nationale"
        if SportingAchievement.Level.REGIONAL in verified_levels:
            return "Espoir Régional"
        return "Héros Local"


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


class AthletePhoto(BaseModel):
    """Store gallery photos associated with an athlete profile."""

    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="athlete_gallery/")
    caption = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "created_at")

    def __str__(self):
        return f"Photo for {self.athlete.full_name}"


class SportingAchievement(BaseModel):
    """Palmarès sportif d'un athlète avec système de vérification ("Trust").

    Chaque résultat est soumis à vérification avant d'être pris en compte dans
    le score commercial de l'athlète.  La preuve via ``proof_url`` permet à
    l'équipe (ou à un script) de valider les performances déclarées.

    Attributes:
        athlete (Athlete): Athlète auquel appartient ce résultat.
        title (str): Intitulé du résultat (ex : "Champion Régional Île-de-France").
        date (datetime.date): Date de la compétition.
        level (str): Niveau géographique de la compétition.
        ranking (str): Classement obtenu (ex : "1er", "Top 10", "Finaliste").
        proof_url (str): URL vers les résultats officiels de la fédération.
        verification_status (str): État de la vérification par le staff.
    """

    class Level(models.TextChoices):
        LOCAL = "local", "Local"
        REGIONAL = "regional", "Régional"
        NATIONAL = "national", "National"
        INTERNATIONAL = "international", "International"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "En attente de vérification"
        VERIFIED = "verified", "Vérifié ✓"
        REJECTED = "rejected", "Rejeté"

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="achievements",
    )
    title = models.CharField(max_length=255)
    date = models.DateField()
    level = models.CharField(max_length=16, choices=Level.choices)
    ranking = models.CharField(
        max_length=64,
        blank=True,
        help_text="Classement obtenu (ex : '1er', 'Top 10', 'Demi-finaliste').",
    )
    proof_url = models.URLField(
        blank=True,
        help_text="Lien vers les résultats officiels de la fédération ou de l'organisateur.",
    )
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )

    class Meta:
        ordering = ("-date",)
        indexes = [
            # Filtre principal pour le calcul du sponsorship_tier.
            models.Index(
                fields=["athlete", "verification_status"],
                name="achievement_athlete_status_idx",
            ),
            models.Index(
                fields=["athlete", "level"],
                name="achievement_athlete_level_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.title} – {self.get_level_display()} ({self.athlete.full_name})"


class UpcomingEvent(BaseModel):
    """Événement sportif à venir montrant la visibilité physique de l'athlète.

    Cette donnée est la plus précieuse pour les sponsors locaux : elle indique
    précisément où, quand et devant quel public leur logo sera exposé dans le
    monde réel.

    Attributes:
        athlete (Athlete): Athlète participant à cet événement.
        event_name (str): Nom de la compétition ou manifestation.
        start_date (datetime.date): Date de début.
        end_date (datetime.date): Date de fin (égale à start_date pour un seul jour).
        location (str): Ville / Région / Pays (ex : "Paris, Île-de-France").
        estimated_physical_audience (int): Nombre de spectateurs attendus sur place.
        target_demographic (str): Profil du public (ex : "Familles, B2B, Jeunes 15-25").
        is_broadcasted (bool): True si l'événement est filmé / streamé.
    """

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="upcoming_events",
    )
    event_name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(
        max_length=255,
        help_text="Ville, région ou pays (ex : 'Bordeaux, Nouvelle-Aquitaine').",
    )
    estimated_physical_audience = models.PositiveIntegerField(
        default=0,
        help_text="Nombre estimé de spectateurs présents physiquement.",
    )
    target_demographic = models.CharField(
        max_length=255,
        blank=True,
        help_text="Profil du public cible (ex : 'Familles', 'B2B', 'Jeunes 15-25 ans').",
    )
    is_broadcasted = models.BooleanField(
        default=False,
        help_text="True si l'événement fait l'objet d'une captation vidéo ou d'un stream.",
    )

    class Meta:
        ordering = ("start_date",)
        indexes = [
            # Filtre principal pour la priorité géographique dans les cards.
            models.Index(
                fields=["athlete", "start_date"],
                name="event_athlete_start_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="event_end_date_gte_start_date",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.event_name} – {self.start_date} ({self.athlete.full_name})"


class SponsorshipAsset(BaseModel):
    """Espace publicitaire précis que l'athlète met en vente.

    L'inventaire transforme la plateforme d'un "Tinder du sport" en une
    véritable marketplace B2B : chaque asset est un "produit" avec une
    fourchette de prix, ce qui supprime la friction mentale de l'acheteur.

    Attributes:
        athlete (Athlete): Athlète propriétaire de l'asset.
        asset_type (str): Catégorie de l'espace publicitaire.
        name (str): Libellé précis de l'espace (ex : "Logo épaule gauche – kimono").
        description (str): Description détaillée (dimensions, conditions, fréquence).
        estimated_value_min (decimal.Decimal): Borne basse de la fourchette tarifaire.
        estimated_value_max (decimal.Decimal): Borne haute de la fourchette tarifaire.
        is_available (bool): True si l'espace est disponible à la vente.
    """

    class AssetType(models.TextChoices):
        PHYSICAL_GEAR = (
            "physical_gear",
            "Équipement physique (logo sur tenue / matériel)",
        )
        DIGITAL_SHOUTOUT = (
            "digital_shoutout",
            "Publication digitale (réseaux / newsletter)",
        )
        EVENT_PRESENCE = (
            "event_presence",
            "Présence physique (inauguration, activation)",
        )
        IMAGE_RIGHTS = "image_rights", "Droit à l'image (campagne photo / vidéo)"

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="sponsorship_assets",
    )
    asset_type = models.CharField(max_length=32, choices=AssetType.choices)
    name = models.CharField(
        max_length=255,
        help_text="Libellé commercial de l'espace (ex : 'Logo épaule gauche sur le kimono').",
    )
    description = models.TextField(
        help_text="Détails : dimensions, conditions d'utilisation, fréquence d'exposition.",
    )
    estimated_value_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Borne basse de la fourchette tarifaire en euros.",
    )
    estimated_value_max = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Borne haute de la fourchette tarifaire en euros.",
    )
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ("asset_type", "name")
        indexes = [
            models.Index(
                fields=["athlete", "is_available"],
                name="asset_athlete_available_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    estimated_value_max__gte=models.F("estimated_value_min")
                ),
                name="asset_value_max_gte_min",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.athlete.full_name})"


class RepresentationMandate(BaseModel):
    """Granular permission grant linking an athlete to one of their entourage members.

    This through model replaces the exclusive ``agent`` foreign key with a
    many-to-many relationship that encodes *what* a person is allowed to do on
    behalf of an athlete, not just that they exist in the system.

    Legal compliance rules are enforced in ``clean()``:

    * **Rule 1 — No unlicensed commissions** (Art. L222-5 Code du sport):
      Any representative whose ``role`` is not ``LICENSED_AGENT`` must have
      ``commission_percentage == 0``.  This makes it technically impossible for
      the platform to facilitate illegal sports-agent activity.

    * **Rule 2 — Minor athlete signing rights**: A ``COACH`` or
      ``CLUB_OFFICIAL`` cannot be granted ``can_sign_legally`` for an athlete
      who is under 18.  Only a ``PARENT_GUARDIAN`` (or the athlete's own
      representative once they reach majority) may hold signing authority.

    Attributes:
        athlete: The athlete being represented.
        representative: The entourage member holding this mandate.
        role: The legal/practical function of the representative.
        can_manage_messaging: Permission to reply to sponsors in the messaging
            module.
        can_negotiate_contracts: Permission to open, edit, and counter-propose
            contract clauses.
        can_sign_legally: Permission to sign contracts with legal effect.
            Blocked for coaches and club officials when the athlete is a minor.
        commission_percentage: Agreed commission rate (0.00–20.00 %).  Must be
            zero for any role other than ``LICENSED_AGENT``.
        is_active: Soft flag allowing a mandate to be suspended without
            deletion, preserving the audit trail.
    """

    class Role(models.TextChoices):
        PARENT_GUARDIAN = "parent_guardian", "Parent / Legal Guardian"
        COACH = "coach", "Coach"
        CLUB_OFFICIAL = "club_official", "Club Official"
        LICENSED_AGENT = "licensed_agent", "Licensed Sports Agent"
        MANAGER = "manager", "Manager"

    # Roles that are prohibited from receiving any commission under French law.
    _NON_COMMISSION_ROLES: frozenset[str] = frozenset(
        {Role.PARENT_GUARDIAN, Role.COACH, Role.CLUB_OFFICIAL, Role.MANAGER}
    )
    # Roles that cannot hold signing authority over a minor athlete.
    _BLOCKED_SIGNING_ROLES_FOR_MINORS: frozenset[str] = frozenset(
        {Role.COACH, Role.CLUB_OFFICIAL}
    )

    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="entourage_mandates",
    )
    representative = models.ForeignKey(
        RepresentativeProfile,
        on_delete=models.CASCADE,
        related_name="mandates",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    can_manage_messaging = models.BooleanField(
        default=False,
        help_text="May communicate with sponsors via the messaging module.",
    )
    can_negotiate_contracts = models.BooleanField(
        default=False,
        help_text="May open, edit, and counter-propose contract clauses.",
    )
    can_sign_legally = models.BooleanField(
        default=False,
        help_text=(
            "May sign contracts with legal effect.  "
            "Blocked automatically for coaches and club officials when the "
            "athlete is under 18."
        ),
    )
    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Agreed commission rate in percent (0.00–20.00).  Must be 0 for non-agent roles.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Inactive mandates are ignored by permission checks.  "
            "Deactivate rather than delete to preserve the audit trail."
        ),
    )

    class Meta:
        ordering = ("role", "created_at")
        # Each representative may hold exactly one mandate per athlete.
        unique_together = (("athlete", "representative"),)
        indexes = [
            # Primary lookup path: find all active mandates for a given athlete.
            models.Index(
                fields=["athlete", "is_active"],
                name="mandate_athlete_active_idx",
            ),
            # Secondary path: find all athletes a representative manages.
            models.Index(
                fields=["representative", "is_active"],
                name="mandate_rep_active_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return (
            f"{self.representative} → {self.athlete.full_name} "
            f"[{self.get_role_display()}]"
        )

    def _athlete_is_minor(self) -> bool:
        """Return True when the linked athlete has not yet reached legal majority.

        Uses the athlete's ``birth_date`` to compute the 18th birthday according
        to French civil law (Art. 488 Code civil).  Athletes born on 29 February
        reach majority on 1 March of the relevant year.

        Returns:
            bool: ``True`` when the athlete is under 18 years old today.
        """
        from datetime import date

        birth = self.athlete.birth_date
        try:
            majority_date = date(birth.year + 18, birth.month, birth.day)
        except ValueError:
            # 29 Feb → majority falls on 1 Mar in non-leap years.
            majority_date = date(birth.year + 18, 3, 1)
        return date.today() < majority_date

    def clean(self) -> None:
        """Enforce mandatory legal constraints on mandate creation and updates.

        Raises:
            django.core.exceptions.ValidationError: When the submitted data
                violates a legal rule (see class docstring for the full list).
        """
        from decimal import Decimal

        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}

        # --- Rule 1: Non-licensed representatives cannot receive a commission ---
        # (Art. L222-5 Code du sport — exercice illégal de la profession d'agent sportif)
        if (
            self.role in self._NON_COMMISSION_ROLES
            and self.commission_percentage is not None
            and self.commission_percentage > Decimal("0.00")
        ):
            errors["commission_percentage"] = (
                f"Representatives with role '{self.get_role_display()}' cannot receive "
                "a commission.  Only a licensed sports agent may charge fees "
                "(Art. L222-5 Code du sport).  Set commission_percentage to 0."
            )

        # --- Rule 2: Coaches and club officials cannot sign for minor athletes ---
        if (
            self.can_sign_legally
            and self.role in self._BLOCKED_SIGNING_ROLES_FOR_MINORS
            and self.athlete_id  # guard against unsaved athlete
            and self._athlete_is_minor()
        ):
            errors["can_sign_legally"] = (
                f"A '{self.get_role_display()}' cannot hold signing authority over "
                "an athlete who is under 18.  Only a PARENT_GUARDIAN may sign on "
                "behalf of a minor athlete (Art. L221-1 Code civil)."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        """Run full validation before persisting the mandate."""
        self.full_clean()
        super().save(*args, **kwargs)
