"""Serializers for the follows application."""

from rest_framework import serializers

from athletes.serializers import AthletePublicSerializer

from .models import Follow


class FollowSerializer(serializers.ModelSerializer):
    """Serialize the follower relationship along with athlete details."""

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
        read_only_fields = fields
