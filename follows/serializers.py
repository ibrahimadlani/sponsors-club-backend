"""Serializers for translating follow records to API payloads."""

from rest_framework import serializers

from athletes.serializers import AthletePublicSerializer

from .models import Follow


class FollowSerializer(serializers.ModelSerializer):
    """Expose follow details tailored for collaborator dashboards.

    The serializer intentionally surfaces read-only fields because follow
    creation is handled by dedicated endpoints. Serializing the embedded
    athlete gives clients immediate access to presentation data without
    triggering additional requests.
    """

    athlete = AthletePublicSerializer(read_only=True)

    class Meta:
        """Serializer configuration."""

        model = Follow
        fields = (
            "id",
            "athlete",
            "notify_news",
            "notify_stats",
            "notify_contracts",
            "created_at",
        )
        # All fields are read-only because follow preferences are currently
        # managed exclusively through follow/unfollow endpoints.
        read_only_fields = fields
