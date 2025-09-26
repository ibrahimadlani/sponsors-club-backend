"""Utility helpers for athletes endpoints to keep views lean and reusable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from .models import Athlete, Sport
from .serializers import (
    AthleteCardSerializer,
    AthletePhotoSerializer,
    SportDisciplineSerializer,
    SportSerializer,
)


def base_athlete_queryset() -> QuerySet[Athlete]:
    """Return the shared queryset configured for athlete endpoints."""

    return (
        Athlete.objects.select_related("sport", "agent__user")
        .prefetch_related("disciplines", "photos")
        .all()
    )


def my_athletes_queryset(agent_profile) -> QuerySet[Athlete]:
    """Return athletes owned by the provided agent profile."""

    return base_athlete_queryset().filter(agent=agent_profile)


@dataclass(frozen=True)
class AthleteCardFilters:
    """Filter options supported by the athlete card endpoint."""

    search: Optional[str] = None
    sport_id: Optional[str] = None


def athlete_cards_payload(filters: AthleteCardFilters) -> dict:
    """Build the response payload used by the public athlete cards endpoint."""

    queryset = (
        Athlete.objects.select_related("sport")
        .prefetch_related("photos", "disciplines")
        .order_by("full_name")
    )
    if filters.search:
        queryset = queryset.filter(full_name__icontains=filters.search)
    if filters.sport_id:
        queryset = queryset.filter(sport_id=filters.sport_id)

    serializer = AthleteCardSerializer(queryset, many=True)
    data = serializer.data
    payload = {
        "count": len(data),
        "results": data,
        "empty_state": len(data) == 0,
    }
    if not data:
        payload["message"] = "Aucun athlète n'est disponible pour le moment."
    return payload


def sport_list_payload() -> Iterable[dict]:
    """Return serialized sports for the public sports listing."""

    sports = Sport.objects.all().prefetch_related("disciplines").order_by("name")
    return SportSerializer(sports, many=True).data


def sport_disciplines_payload(sport_id: str) -> dict:
    """Return serialized data for a single sport and its disciplines."""

    sport = get_object_or_404(Sport.objects.prefetch_related("disciplines"), pk=sport_id)
    disciplines = sport.disciplines.order_by("name")
    return {
        "sport": SportSerializer(sport, context={"include_disciplines": False}).data,
        "disciplines": SportDisciplineSerializer(disciplines, many=True).data,
    }


def athlete_photos_payload(athlete_id: str) -> dict:
    """Return the serialized gallery for the requested athlete."""

    athlete = get_object_or_404(
        Athlete.objects.prefetch_related("photos"),
        pk=athlete_id,
    )
    photos = athlete.photos.all()
    return {
        "athlete_id": str(athlete.id),
        "photos": AthletePhotoSerializer(photos, many=True).data,
    }
