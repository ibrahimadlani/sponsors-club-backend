"""Serializers powering athlete CRUD and public views."""

# Serializers centralise validation so views and signals can remain slim.

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

from .models import Athlete, AthletePhoto, Sport, SportDiscipline


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


class AthletePublicSerializer(serializers.ModelSerializer):
    """Expose a limited athlete payload for public endpoints."""

    sport = SportSerializer(read_only=True)
    disciplines = SportDisciplineSerializer(many=True, read_only=True)
    card_photos = serializers.SerializerMethodField()
    gallery_photos = AthletePhotoSerializer(source="photos", many=True, read_only=True)

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
            "followers_count_cached",
            "engagement_rate_cached",
            "avatar",
            "card_photos",
            "gallery_photos",
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

    @staticmethod
    def _photo_url_or_name(photo: AthletePhoto) -> str:
        """Return a safe path or URL for the provided photo."""

        try:
            return photo.image.url
        except ValueError:  # pragma: no cover - storage without MEDIA_URL fallback
            return photo.image.name


class AthleteCardSerializer(AthletePublicSerializer):
    """Lightweight representation for athlete listings with key metrics."""

    followers_total = serializers.SerializerMethodField()
    engagement_rate = serializers.SerializerMethodField()

    class Meta(AthletePublicSerializer.Meta):
        fields = (
            "id",
            "slug",
            "full_name",
            "country",
            "city",
            "sport",
            "disciplines",
            "avatar",
            "card_photos",
            "gallery_photos",
            "followers_total",
            "engagement_rate",
        )
        read_only_fields = fields

    def get_followers_total(self, athlete: Athlete) -> int:
        return athlete.followers_count_cached

    def get_engagement_rate(self, athlete: Athlete) -> float:
        if athlete.engagement_rate_cached is None:
            return 0.0
        return float(athlete.engagement_rate_cached)


class AthleteSerializer(serializers.ModelSerializer):
    """Full serializer used for authenticated athlete management.

    The serializer embeds plan-based constraints and ensures ownership rules
    are respected when creating or updating athletes.
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
    # FileField keeps uploads lightweight so tests don't depend on Pillow.
    new_photos = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        write_only=True,
        required=False,
    )
    card_photos = serializers.SerializerMethodField()

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
                {"discipline_ids": "Sport must be specified when selecting disciplines."}
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
