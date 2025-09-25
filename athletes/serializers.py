"""Serializers powering athlete CRUD and public views."""

# Serializers centralise validation so views and signals can remain slim.

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.feature_matrix import AGENT_FEATURES
from core.permissions import (
    get_agent_plan_features,
    requirement_denied_payload,
    user_feature_requirement,
)
from users.models import AgentProfile

from .models import Athlete, Sport


class SportSerializer(serializers.ModelSerializer):
    """Serialize sport metadata for read operations."""

    class Meta:
        model = Sport
        fields = ("id", "name", "discipline")


class AthletePublicSerializer(serializers.ModelSerializer):
    """Expose a limited athlete payload for public endpoints."""

    sport = SportSerializer(read_only=True)

    class Meta:
        model = Athlete
        fields = (
            "id",
            "full_name",
            "sport",
            "nationality",
            "followers_count_cached",
            "engagement_rate_cached",
            "avatar",
        )
        read_only_fields = fields


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

    class Meta:
        model = Athlete
        fields = (
            "id",
            "sport",
            "sport_id",
            "agent",
            "full_name",
            "birth_date",
            "nationality",
            "bio",
            "social_links",
            "followers_count_cached",
            "engagement_rate_cached",
            "avatar",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "agent",
            "followers_count_cached",
            "engagement_rate_cached",
            "created_at",
            "updated_at",
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
        athlete = Athlete.objects.create(
            agent=agent_profile,
            **validated_data,
        )
        return athlete

    def update(self, instance, validated_data):
        """Update an athlete without allowing agent reassignment.

        Args:
            instance (athletes.models.Athlete): Athlete being updated.
            validated_data (dict): Cleaned fields provided in the request.

        Returns:
            athletes.models.Athlete: Updated athlete instance.
        """
        validated_data.pop("agent", None)
        # Defer to DRF's default implementation once agent ownership is frozen.
        return super().update(instance, validated_data)
