"""Serializers backing analytics endpoints."""

from rest_framework import serializers

from .models import AthleteStat


class AthleteStatSerializer(serializers.ModelSerializer):
    """Serialize athlete statistic records for read operations."""

    class Meta:
        model = AthleteStat
        fields = (
            "id",
            "athlete",
            "metric",
            "value",
            "date",
            "extra",
            "created_at",
        )
        read_only_fields = ("id", "athlete", "created_at")


class AthleteStatCreateSerializer(serializers.ModelSerializer):
    """Validate incoming payloads for creating athlete stats."""

    class Meta:
        model = AthleteStat
        fields = ("metric", "value", "date", "extra")

    def validate(self, attrs):
        attrs.setdefault("extra", {})
        return attrs


class AthleteStatAggregateSerializer(serializers.Serializer):
    """Represent aggregated datapoints returned by analytics endpoints."""

    metric = serializers.CharField()
    value = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateField()
    extra = serializers.JSONField()

    def create(self, validated_data):
        raise NotImplementedError("Aggregate serializer is read-only.")

    def update(self, instance, validated_data):
        raise NotImplementedError("Aggregate serializer is read-only.")


class AthleteStatsBatchRequestSerializer(serializers.Serializer):
    """Parse batch statistics query parameters."""

    athlete_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )
    metrics = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )

    def create(self, validated_data):
        raise NotImplementedError("Batch request serializer is read-only.")

    def update(self, instance, validated_data):
        raise NotImplementedError("Batch request serializer is read-only.")
