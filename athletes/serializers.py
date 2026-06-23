"""Serializers powering athlete CRUD and public views."""

# Serializers centralise validation so views and signals can remain slim.

from typing import Optional

from django.db.models import Max
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.feature_matrix import AGENT_FEATURES
from core.permissions import (
    get_agent_plan_features,
    requirement_denied_payload,
    user_feature_requirement,
)
from users.models import AgentProfile

from .models import (
    Athlete,
    AthletePhoto,
    Sport,
    SportDiscipline,
    SportingAchievement,
    SponsorshipAsset,
    UpcomingEvent,
)


class SportDisciplineSerializer(serializers.ModelSerializer):
    """Expose individual discipline metadata within a sport."""

    class Meta:
        model = SportDiscipline
        fields = ("id", "name", "slug", "description", "is_olympic")


class SportSerializer(serializers.ModelSerializer):
    """Serialize sport metadata for read operations."""

    disciplines = SportDisciplineSerializer(many=True, read_only=True)

    class Meta:
        model = Sport
        fields = (
            "id",
            "name",
            "slug",
            "emoji",
            "category",
            "disciplines",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("include_disciplines", True):
            data.pop("disciplines", None)
        return data


class AthletePhotoSerializer(serializers.ModelSerializer):
    """Represent individual gallery photos for an athlete."""

    class Meta:
        model = AthletePhoto
        fields = ("id", "image", "caption", "position", "created_at")
        read_only_fields = ("id", "created_at")


class SportingAchievementSerializer(serializers.ModelSerializer):
    """Sérialise un résultat sportif avec son statut de vérification.

    Seuls les résultats ``VERIFIED`` sont exposés sur les endpoints publics ;
    l'intégralité est disponible pour les agents authentifiés.
    """

    level_label = serializers.CharField(source="get_level_display", read_only=True)
    verification_status_label = serializers.CharField(
        source="get_verification_status_display", read_only=True
    )

    class Meta:
        model = SportingAchievement
        fields = (
            "id",
            "title",
            "date",
            "level",
            "level_label",
            "ranking",
            "proof_url",
            "verification_status",
            "verification_status_label",
            "created_at",
        )
        read_only_fields = (
            "id",
            "level_label",
            "verification_status_label",
            "created_at",
        )


class UpcomingEventSerializer(serializers.ModelSerializer):
    """Sérialise un événement à venir et expose la visibilité physique de l'athlète."""

    class Meta:
        model = UpcomingEvent
        fields = (
            "id",
            "event_name",
            "start_date",
            "end_date",
            "location",
            "estimated_physical_audience",
            "target_demographic",
            "is_broadcasted",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate(self, attrs):
        """Ensure end_date is not before start_date.

        Args:
            attrs (dict): Validated field values.

        Returns:
            dict: Unchanged attributes when the constraint is met.

        Raises:
            serializers.ValidationError: When ``end_date`` precedes ``start_date``.
        """
        if attrs.get("end_date") and attrs.get("start_date"):
            if attrs["end_date"] < attrs["start_date"]:
                raise serializers.ValidationError(
                    {
                        "end_date": "La date de fin ne peut pas précéder la date de début."
                    }
                )
        return attrs


class SponsorshipAssetSerializer(serializers.ModelSerializer):
    """Sérialise un espace publicitaire (inventaire) de l'athlète."""

    asset_type_label = serializers.CharField(
        source="get_asset_type_display", read_only=True
    )

    class Meta:
        model = SponsorshipAsset
        fields = (
            "id",
            "asset_type",
            "asset_type_label",
            "name",
            "description",
            "estimated_value_min",
            "estimated_value_max",
            "is_available",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "asset_type_label", "created_at", "updated_at")

    def validate(self, attrs):
        """Ensure value_max is not less than value_min.

        Args:
            attrs (dict): Validated field values.

        Returns:
            dict: Unchanged attributes when the constraint is met.

        Raises:
            serializers.ValidationError: When max < min.
        """
        v_min = attrs.get("estimated_value_min")
        v_max = attrs.get("estimated_value_max")
        if v_min is not None and v_max is not None and v_max < v_min:
            raise serializers.ValidationError(
                {
                    "estimated_value_max": (
                        "La valeur maximale doit être supérieure ou égale à la valeur minimale."
                    )
                }
            )
        return attrs


class AgentPublicSerializer(serializers.Serializer):
    """Expose public agent information for athlete profiles."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    avatar = serializers.ImageField(source="user.avatar", read_only=True)


class AthletePublicSerializer(serializers.ModelSerializer):
    """Expose a limited athlete payload for public endpoints.

    Inclut le palmarès vérifié, les événements à venir et l'inventaire des
    espaces de sponsoring en plus des informations de profil de base.
    """

    sport = SportSerializer(read_only=True)
    disciplines = SportDisciplineSerializer(many=True, read_only=True)
    agent = AgentPublicSerializer(read_only=True)
    card_photos = serializers.SerializerMethodField()
    gallery_photos = AthletePhotoSerializer(source="photos", many=True, read_only=True)
    verified_achievements = serializers.SerializerMethodField()
    upcoming_events = serializers.SerializerMethodField()
    available_assets = serializers.SerializerMethodField()
    total_physical_reach = serializers.SerializerMethodField()
    sponsorship_tier = serializers.SerializerMethodField()

    class Meta:
        model = Athlete
        fields = (
            "id",
            "slug",
            "full_name",
            "country",
            "city",
            "sport",
            "disciplines",
            "nationality",
            "club_name",
            "federation_name",
            "agent",
            "avatar",
            "card_photos",
            "gallery_photos",
            "verified_achievements",
            "upcoming_events",
            "available_assets",
            "total_physical_reach",
            "sponsorship_tier",
        )
        read_only_fields = fields

    def get_card_photos(self, athlete: Athlete) -> list[str]:
        """Return up to three gallery photo URLs for carousel displays."""

        photos = getattr(athlete, "_prefetched_objects_cache", {}).get("photos")
        queryset = photos if photos is not None else athlete.photos.all()
        return [
            self._photo_url_or_name(photo)
            for photo in list(queryset)[:3]
            if photo.image
        ]

    def get_verified_achievements(self, athlete: Athlete) -> list[dict]:
        """Return only staff-verified achievements for public display.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            list[dict]: Serialized achievements with verification_status=VERIFIED.
        """
        cache = getattr(athlete, "_prefetched_objects_cache", {})
        if "achievements" in cache:
            verified = [
                a
                for a in cache["achievements"]
                if a.verification_status
                == SportingAchievement.VerificationStatus.VERIFIED
            ]
        else:
            verified = list(
                athlete.achievements.filter(
                    verification_status=SportingAchievement.VerificationStatus.VERIFIED
                )
            )
        return SportingAchievementSerializer(verified, many=True).data

    def get_upcoming_events(self, athlete: Athlete) -> list[dict]:
        """Return future events sorted by start_date ascending.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            list[dict]: Serialized UpcomingEvent records from today onwards.
        """
        from django.utils import timezone

        today = timezone.now().date()
        cache = getattr(athlete, "_prefetched_objects_cache", {})
        if "upcoming_events" in cache:
            events = sorted(
                [e for e in cache["upcoming_events"] if e.start_date >= today],
                key=lambda e: e.start_date,
            )
        else:
            events = list(athlete.upcoming_events.filter(start_date__gte=today))
        return UpcomingEventSerializer(events, many=True).data

    def get_available_assets(self, athlete: Athlete) -> list[dict]:
        """Return only available sponsorship assets.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            list[dict]: Serialized SponsorshipAsset records where is_available=True.
        """
        cache = getattr(athlete, "_prefetched_objects_cache", {})
        if "sponsorship_assets" in cache:
            assets = [a for a in cache["sponsorship_assets"] if a.is_available]
        else:
            assets = list(athlete.sponsorship_assets.filter(is_available=True))
        return SponsorshipAssetSerializer(assets, many=True).data

    def get_total_physical_reach(self, athlete: Athlete) -> int:
        """Return the total_physical_reach property value.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            int: Summed physical audience across all future events.
        """
        return athlete.total_physical_reach

    def get_sponsorship_tier(self, athlete: Athlete) -> str:
        """Return the sponsorship_tier property value.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            str: One of ``"Élite Nationale"``, ``"Espoir Régional"``,
            ``"Héros Local"``.
        """
        return athlete.sponsorship_tier

    @staticmethod
    def _photo_url_or_name(photo: AthletePhoto) -> str:
        """Return a safe path or URL for the provided photo."""

        try:
            return photo.image.url
        except ValueError:  # pragma: no cover - storage without MEDIA_URL fallback
            return photo.image.name


class AthleteCardSerializer(AthletePublicSerializer):
    """Lightweight representation for athlete discovery cards.

    Pivote des métriques sociales (followers) vers les métriques business :
    tier de sponsoring, visibilité physique totale, prochain événement et
    nombre d'espaces disponibles à l'achat.
    """

    next_event = serializers.SerializerMethodField()
    available_asset_count = serializers.SerializerMethodField()

    class Meta(AthletePublicSerializer.Meta):
        fields = (
            "id",
            "slug",
            "full_name",
            "country",
            "city",
            "club_name",
            "sport",
            "disciplines",
            "avatar",
            "card_photos",
            "sponsorship_tier",
            "total_physical_reach",
            "next_event",
            "available_asset_count",
        )
        read_only_fields = fields

    def get_next_event(self, athlete: Athlete) -> Optional[dict]:
        """Return the earliest upcoming event, or None.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            dict | None: Serialized UpcomingEvent or ``None`` when no future
            events are scheduled.
        """
        from django.utils import timezone

        today = timezone.now().date()
        cache = getattr(athlete, "_prefetched_objects_cache", {})
        if "upcoming_events" in cache:
            future = sorted(
                [e for e in cache["upcoming_events"] if e.start_date >= today],
                key=lambda e: e.start_date,
            )
            event = future[0] if future else None
        else:
            event = athlete.upcoming_events.filter(start_date__gte=today).first()
        return UpcomingEventSerializer(event).data if event else None

    def get_available_asset_count(self, athlete: Athlete) -> int:
        """Return the number of sponsorship assets currently available.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            int: Count of SponsorshipAsset records where is_available=True.
        """
        cache = getattr(athlete, "_prefetched_objects_cache", {})
        if "sponsorship_assets" in cache:
            return sum(1 for a in cache["sponsorship_assets"] if a.is_available)
        return athlete.sponsorship_assets.filter(is_available=True).count()


class AthleteSerializer(serializers.ModelSerializer):
    """Full serializer used for authenticated athlete management.

    The serializer embeds plan-based constraints and ensures ownership rules
    are respected when creating or updating athletes.  Includes institutional
    identity fields (club, federation, license) and read-only computed
    business metrics.
    """

    sport = SportSerializer(read_only=True)
    sport_id = serializers.PrimaryKeyRelatedField(
        queryset=Sport.objects.all(),
        source="sport",
        write_only=True,
    )
    disciplines = SportDisciplineSerializer(many=True, read_only=True)
    discipline_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SportDiscipline.objects.all(),
        write_only=True,
        required=False,
    )
    photos = AthletePhotoSerializer(many=True, read_only=True)
    new_photos = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        write_only=True,
        required=False,
    )
    card_photos = serializers.SerializerMethodField()
    achievements = SportingAchievementSerializer(many=True, read_only=True)
    upcoming_events = UpcomingEventSerializer(many=True, read_only=True)
    sponsorship_assets = SponsorshipAssetSerializer(many=True, read_only=True)
    total_physical_reach = serializers.SerializerMethodField()
    sponsorship_tier = serializers.SerializerMethodField()

    class Meta:
        model = Athlete
        fields = (
            "id",
            "slug",
            "sport",
            "sport_id",
            "agent",
            "full_name",
            "birth_date",
            "nationality",
            "country",
            "city",
            "bio",
            "social_links",
            # Identité institutionnelle
            "club_name",
            "federation_name",
            "license_number",
            "disciplines",
            "discipline_ids",
            "followers_count_cached",
            "engagement_rate_cached",
            "avatar",
            "created_at",
            "updated_at",
            "photos",
            "new_photos",
            "card_photos",
            # Business metrics (lecture seule)
            "achievements",
            "upcoming_events",
            "sponsorship_assets",
            "total_physical_reach",
            "sponsorship_tier",
        )
        read_only_fields = (
            "id",
            "slug",
            "agent",
            "followers_count_cached",
            "engagement_rate_cached",
            "created_at",
            "updated_at",
            "disciplines",
            "photos",
            "card_photos",
            "achievements",
            "upcoming_events",
            "sponsorship_assets",
            "total_physical_reach",
            "sponsorship_tier",
        )

    def validate(self, attrs):
        """Ensure the requesting user can manage the athlete being edited.

        Args:
            attrs (dict): Incoming payload fields that passed individual field
                validation.

        Returns:
            dict: Sanitised attributes ready for persistence.

        Raises:
            rest_framework.serializers.ValidationError: If the user lacks an
                agent profile or tries to reassign ownership.
        """
        request = self.context["request"]
        try:
            agent_profile = request.user.agent_profile
        except AgentProfile.DoesNotExist as exc:
            error = {"non_field_errors": ["Agent profile not found for user."]}
            raise serializers.ValidationError(error) from exc
        if self.instance and self.instance.agent != agent_profile:
            # Prevent reassigning ownership, which could bypass billing checks.
            raise serializers.ValidationError(
                {"agent": "Cannot reassign athlete agent."}
            )
        sport = attrs.get("sport") or (self.instance.sport if self.instance else None)
        discipline_ids = attrs.get("discipline_ids")
        if discipline_ids and sport is None:
            raise serializers.ValidationError(
                {
                    "discipline_ids": "Sport must be specified when selecting disciplines."
                }
            )
        if discipline_ids and sport:
            invalid = [d for d in discipline_ids if d.sport_id != sport.id]
            if invalid:
                raise serializers.ValidationError(
                    {
                        "discipline_ids": "All disciplines must belong to the selected sport.",
                    }
                )
        return attrs

    def validate_nationality(self, value):
        """Validate that nationality is a valid ISO 3166-1 alpha-2 code."""
        if value and len(value) != 2:
            raise serializers.ValidationError(
                "Nationality must be a valid ISO 3166-1 alpha-2 code (2 letters)."
            )
        if value and not value.isalpha():
            raise serializers.ValidationError(
                "Nationality code must contain only letters."
            )
        return value.upper() if value else value

    def validate_country(self, value):
        """Validate that country is a valid ISO 3166-1 alpha-2 code."""
        if value and len(value) != 2:
            raise serializers.ValidationError(
                "Country must be a valid ISO 3166-1 alpha-2 code (2 letters)."
            )
        if value and not value.isalpha():
            raise serializers.ValidationError("Country code must contain only letters.")
        return value.upper() if value else value

    def create(self, validated_data):
        """Create a new athlete while enforcing subscription limits.

        Args:
            validated_data (dict): Cleaned fields ready for insertion.

        Returns:
            athletes.models.Athlete: Newly created athlete instance linked to
            the requesting agent.

        Raises:
            rest_framework.exceptions.PermissionDenied: If the plan does not
                allow creating another athlete.
        """
        request = self.context["request"]
        agent_profile = request.user.agent_profile
        features = get_agent_plan_features(request.user)
        max_athletes = features.get("max_athletes")
        try:
            max_athletes = int(max_athletes)
        except (TypeError, ValueError):
            max_athletes = 0

        requirement, granted = user_feature_requirement(request.user, "athlete_slots")
        requirement = requirement or AGENT_FEATURES["athlete_slots"]
        if not granted and max_athletes <= 0:
            # Construct an informative payload so the frontend can prompt for an
            # upgrade rather than failing silently.
            message = "Athlete limit reached. Upgrade to add more athletes."
            payload = requirement_denied_payload(requirement, message)
            raise PermissionDenied(payload)
        if max_athletes > 0:
            current_count = Athlete.objects.filter(agent=agent_profile).count()
            if current_count >= max_athletes:
                message = "Athlete limit reached. Upgrade to add more athletes."
                payload = requirement_denied_payload(requirement, message)
                raise PermissionDenied(payload)
        discipline_ids = validated_data.pop("discipline_ids", [])
        new_photos = validated_data.pop("new_photos", [])
        athlete = Athlete.objects.create(
            agent=agent_profile,
            **validated_data,
        )
        if discipline_ids:
            athlete.disciplines.set(discipline_ids)
        if new_photos:
            self._attach_photos(athlete, new_photos)
        return athlete

    def update(self, instance, validated_data):
        """Update an athlete without allowing agent reassignment.

        Args:
            instance (athletes.models.Athlete): Athlete being updated.
            validated_data (dict): Cleaned fields provided in the request.

        Returns:
            athletes.models.Athlete: Updated athlete instance.
        """
        discipline_ids = validated_data.pop("discipline_ids", None)
        new_photos = validated_data.pop("new_photos", [])
        validated_data.pop("agent", None)
        athlete = super().update(instance, validated_data)
        if discipline_ids is not None:
            athlete.disciplines.set(discipline_ids)
        if new_photos:
            self._attach_photos(athlete, new_photos)
        return athlete

    def get_card_photos(self, athlete: Athlete) -> list[str]:
        """Expose the carousel-ready photo URLs for authenticated clients."""

        photos = getattr(athlete, "_prefetched_objects_cache", {}).get("photos")
        queryset = photos if photos is not None else athlete.photos.all()
        return [
            AthletePublicSerializer._photo_url_or_name(photo)
            for photo in list(queryset)[:3]
            if photo.image
        ]

    def get_total_physical_reach(self, athlete: Athlete) -> int:
        """Delegate to the model property.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            int: Summed physical audience of future events.
        """
        return athlete.total_physical_reach

    def get_sponsorship_tier(self, athlete: Athlete) -> str:
        """Delegate to the model property.

        Args:
            athlete (Athlete): Athlete instance being serialized.

        Returns:
            str: Commercial tier label.
        """
        return athlete.sponsorship_tier

    def _attach_photos(self, athlete: Athlete, photo_files: list) -> None:
        """Persist uploaded gallery photos while maintaining ordering."""

        if not photo_files:
            return
        current_max = (
            AthletePhoto.objects.filter(athlete=athlete)
            .aggregate(Max("position"))
            .get("position__max")
            or 0
        )
        for offset, upload in enumerate(photo_files, start=1):
            AthletePhoto.objects.create(
                athlete=athlete,
                image=upload,
                position=current_max + offset,
            )
