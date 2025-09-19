"""Serializers powering athlete CRUD and public views."""

# pylint: disable=missing-class-docstring,too-few-public-methods

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
    class Meta:
        model = Sport
        fields = ('id', 'name', 'discipline')


class AthletePublicSerializer(serializers.ModelSerializer):
    sport = SportSerializer(read_only=True)

    class Meta:
        model = Athlete
        fields = (
            'id',
            'full_name',
            'sport',
            'nationality',
            'followers_count_cached',
            'engagement_rate_cached',
            'avatar',
        )
        read_only_fields = fields


class AthleteSerializer(serializers.ModelSerializer):
    sport = SportSerializer(read_only=True)
    sport_id = serializers.PrimaryKeyRelatedField(
        queryset=Sport.objects.all(),  # pylint: disable=no-member
        source='sport',
        write_only=True,
    )

    class Meta:
        model = Athlete
        fields = (
            'id',
            'sport',
            'sport_id',
            'agent',
            'full_name',
            'birth_date',
            'nationality',
            'bio',
            'social_links',
            'is_self_represented',
            'followers_count_cached',
            'engagement_rate_cached',
            'avatar',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'agent',
            'followers_count_cached',
            'engagement_rate_cached',
            'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        request = self.context['request']
        try:
            agent_profile = request.user.agent_profile
        except AgentProfile.DoesNotExist as exc:  # pylint: disable=no-member
            error = {'non_field_errors': ['Agent profile not found for user.']}
            raise serializers.ValidationError(error) from exc
        if self.instance and self.instance.agent != agent_profile:
            raise serializers.ValidationError({'agent': 'Cannot reassign athlete agent.'})
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        agent_profile = request.user.agent_profile
        features = get_agent_plan_features(request.user)
        max_athletes = features.get('max_athletes')
        try:
            max_athletes = int(max_athletes)
        except (TypeError, ValueError):
            max_athletes = 0

        requirement, granted = user_feature_requirement(request.user, 'athlete_slots')
        requirement = requirement or AGENT_FEATURES['athlete_slots']
        if not granted and max_athletes <= 0:
            message = 'Athlete limit reached. Upgrade to add more athletes.'
            payload = requirement_denied_payload(requirement, message)
            raise PermissionDenied(payload)
        if max_athletes > 0:
            current_count = Athlete.objects.filter(  # pylint: disable=no-member
                agent=agent_profile
            ).count()
            if current_count >= max_athletes:
                message = 'Athlete limit reached. Upgrade to add more athletes.'
                payload = requirement_denied_payload(requirement, message)
                raise PermissionDenied(payload)
        athlete = Athlete.objects.create(  # pylint: disable=no-member
            agent=agent_profile,
            **validated_data,
        )
        return athlete

    def update(self, instance, validated_data):
        validated_data.pop('agent', None)
        return super().update(instance, validated_data)
