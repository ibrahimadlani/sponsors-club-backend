"""Serializers backing social media analytics endpoints."""

from rest_framework import serializers

from athletes.serializers import AthletePublicSerializer

from .models import AthleteSocialAccount, DailyStats, SocialPlatform


class SocialPlatformSerializer(serializers.ModelSerializer):
    """Serialize social platform definitions."""

    class Meta:
        model = SocialPlatform
        fields = ("id", "name", "base_url", "created_at", "updated_at")
        read_only_fields = fields


class AthleteSocialAccountSerializer(serializers.ModelSerializer):
    """Serialize social account details alongside athlete and platform."""

    platform = SocialPlatformSerializer(read_only=True)
    athlete = AthletePublicSerializer(read_only=True)

    class Meta:
        model = AthleteSocialAccount
        fields = (
            "id",
            "athlete",
            "platform",
            "username",
            "external_id",
            "access_token",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "athlete",
            "platform",
            "created_at",
            "updated_at",
        )


class DailyStatsSerializer(serializers.ModelSerializer):
    """Expose raw daily metrics for an athlete social account."""

    account = AthleteSocialAccountSerializer(read_only=True)

    class Meta:
        model = DailyStats
        fields = (
            "id",
            "account",
            "date",
            "followers",
            "following",
            "posts_count",
            "likes",
            "comments",
            "shares",
            "views",
            "watch_time",
            "engagement_rate",
            "top_post",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TopPostSerializer(serializers.Serializer):
    """Represent the top performing post for a summary response."""

    post_id = serializers.CharField()
    likes = serializers.IntegerField()
    comments = serializers.IntegerField()
    engagement_rate = serializers.FloatField()


class GraphPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    followers = serializers.IntegerField()
    engagement_rate = serializers.FloatField()


class DailyStatsSummarySerializer(serializers.Serializer):
    """Aggregate summary payload for an athlete and platform."""

    athlete_id = serializers.UUIDField()
    platform = serializers.CharField()
    period = serializers.CharField()
    summary = serializers.DictField(child=serializers.FloatField(), allow_empty=True)
    top_post = TopPostSerializer(allow_null=True, required=False)
    graph_data = GraphPointSerializer(many=True)

    def to_representation(self, instance):
        """Allow passing dictionaries directly without strict serializer models."""

        if isinstance(instance, dict):
            return instance
        return super().to_representation(instance)
