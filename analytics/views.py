"""API views for serving analytics data."""

from collections import defaultdict

from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from athletes.models import Athlete

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import (
    collaborator_meets_requirement,
    get_agent_profile,
    requirement_denied_payload,
)
from .models import AthleteStat
from .serializers import (
    AthleteStatCreateSerializer,
    AthleteStatSerializer,
    AthleteStatsBatchRequestSerializer,
)


ATHLETE_STATS_REQUIREMENT = COLLABORATOR_FEATURES['athlete_stats_all']


def _user_can_view_athlete_stats(user, athlete):
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    agent_profile = get_agent_profile(user)
    if agent_profile and athlete.agent_id == agent_profile.id:
        return True
    return collaborator_meets_requirement(user, ATHLETE_STATS_REQUIREMENT)


def _user_can_modify_athlete_stats(user, athlete):
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    agent_profile = get_agent_profile(user)
    return agent_profile is not None and athlete.agent_id == agent_profile.id


def _user_can_access_stats_batch(user, athlete_ids):
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    agent_profile = get_agent_profile(user)
    if agent_profile:
        owned_ids = set(
            Athlete.objects.filter(
                agent=agent_profile
            ).values_list('id', flat=True)
        )
        if set(athlete_ids).issubset(owned_ids):
            return True
    return collaborator_meets_requirement(user, ATHLETE_STATS_REQUIREMENT)


def _latest_stats_for_athlete(athlete):
    stats = AthleteStat.objects.filter(
        athlete=athlete
    ).order_by('-date')
    latest_by_metric = {}
    for stat in stats:
        latest_by_metric.setdefault(stat.metric, stat)
    # Sort to provide deterministic output order
    return [latest_by_metric[key] for key in sorted(latest_by_metric.keys())]


class AthleteStatsView(APIView):
    """Read and write daily athlete statistics."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, athlete_id):
        """Return the latest stats for the requested athlete."""
        athlete = Athlete.objects.filter(id=athlete_id).first()
        if not athlete:
            return Response({'detail': 'Athlete not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not _user_can_view_athlete_stats(request.user, athlete):
            payload = requirement_denied_payload(
                ATHLETE_STATS_REQUIREMENT,
                'Stats access restricted to owning agents or subscribed organisations.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        latest_stats = _latest_stats_for_athlete(athlete)
        serializer = AthleteStatSerializer(latest_stats, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, athlete_id):
        """Create a new datapoint for the requested athlete."""
        athlete = (
            Athlete.objects.filter(id=athlete_id)
            .select_related('agent')
            .first()
        )
        if not athlete:
            return Response({'detail': 'Athlete not found.'}, status=status.HTTP_404_NOT_FOUND)

        if (
            not request.user.is_staff
            and not _user_can_modify_athlete_stats(request.user, athlete)
        ):
            return Response(
                {'detail': 'Only the athlete agent or staff may add stats.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AthleteStatCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stat = AthleteStat.objects.create(
            athlete=athlete,
            **serializer.validated_data,
        )
        return Response(AthleteStatSerializer(stat).data, status=status.HTTP_201_CREATED)


class AthleteStatsTimeseriesView(APIView):
    """Expose historical stats for a single athlete."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, athlete_id):
        """Return the full time series for the athlete."""
        athlete = Athlete.objects.filter(id=athlete_id).first()
        if not athlete:
            return Response({'detail': 'Athlete not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not _user_can_view_athlete_stats(request.user, athlete):
            payload = requirement_denied_payload(
                ATHLETE_STATS_REQUIREMENT,
                'Stats access restricted to owning agents or subscribed organisations.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        metric_filter = request.query_params.getlist('metric') or None
        qs = AthleteStat.objects.filter(
            athlete_id=athlete_id
        ).order_by('date')
        if metric_filter:
            qs = qs.filter(metric__in=metric_filter)
        serializer = AthleteStatSerializer(qs, many=True)
        return Response(serializer.data)


class AthleteStatsBatchView(APIView):
    """Return the latest stats for a list of athletes."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        """Return the latest stats for a batch of athletes and metrics."""
        serializer = AthleteStatsBatchRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        athlete_ids = data['athlete_ids']
        metrics = data['metrics']

        if not _user_can_access_stats_batch(request.user, athlete_ids):
            payload = requirement_denied_payload(
                ATHLETE_STATS_REQUIREMENT,
                'Stats access restricted to owning agents or subscribed organisations.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        stats = AthleteStat.objects.filter(
            athlete_id__in=athlete_ids,
            metric__in=metrics,
        ).order_by('athlete_id', 'metric', '-date')

        latest_by_metric = {}
        for stat in stats:
            key = (stat.athlete_id, stat.metric)
            if key not in latest_by_metric:
                latest_by_metric[key] = stat

        response_payload = defaultdict(dict)
        for (athlete_id, metric), stat in latest_by_metric.items():
            response_payload[str(athlete_id)][metric] = AthleteStatSerializer(stat).data

        return Response(response_payload)
