"""Utility helpers for athletes endpoints to keep views lean and reusable.

Le moteur de valorisation "Sport-Business" est implémenté ici :
les athlètes ayant des événements à venir dans la région ciblée par le sponsor
sont remontés en tête de liste, indépendamment de leur ordre alphabétique.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db.models import (
    Exists,
    OuterRef,
    QuerySet,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Athlete, Sport, UpcomingEvent
from .serializers import (
    AthleteCardSerializer,
    AthletePhotoSerializer,
    SportDisciplineSerializer,
    SportSerializer,
)


def base_athlete_queryset() -> QuerySet[Athlete]:
    """Return the shared queryset configured for athlete endpoints.

    Prefetches all Sport-Business related models (achievements, upcoming_events,
    sponsorship_assets) to avoid N+1 queries when the properties
    ``total_physical_reach`` and ``sponsorship_tier`` are accessed in serializers.

    Returns:
        QuerySet[Athlete]: Queryset with select_related and prefetch_related
        configured for full profile rendering.
    """
    return (
        Athlete.objects.select_related("sport", "agent__user")
        .prefetch_related(
            "disciplines",
            "photos",
            "achievements",
            "upcoming_events",
            "sponsorship_assets",
        )
        .all()
    )


def my_athletes_queryset(agent_profile) -> QuerySet[Athlete]:
    """Return athletes owned by the provided agent profile.

    Args:
        agent_profile (AgentProfile): The agent whose athletes are requested.

    Returns:
        QuerySet[Athlete]: Filtered and prefetch-optimised queryset.
    """
    return base_athlete_queryset().filter(agent=agent_profile)


@dataclass(frozen=True)
class AthleteCardFilters:
    """Filter options supported by the athlete card endpoint.

    Attributes:
        search (str | None): Case-insensitive substring match on ``full_name``.
        sport_id (str | None): UUID of the sport to filter by.
        region (str | None): Free-text region / city used to surface athletes
            whose upcoming events are held in that area.  Matched
            case-insensitively against ``UpcomingEvent.location``.
    """

    search: Optional[str] = None
    sport_id: Optional[str] = None
    region: Optional[str] = None


def athlete_cards_payload(filters: AthleteCardFilters) -> dict:
    """Build the response payload for the public athlete discovery endpoint.

    Sorting strategy:
    1. When ``filters.region`` is provided, athletes with at least one upcoming
       event in that region appear first (annotated boolean ``has_regional_event``).
    2. Within each group, athletes are sorted alphabetically by ``full_name``.

    The ``Exists`` subquery avoids loading all events into Python memory and
    lets the database engine handle the priority efficiently.

    Args:
        filters (AthleteCardFilters): Active filter configuration.

    Returns:
        dict: Payload with ``count``, ``results``, and ``empty_state`` keys.
    """
    today = timezone.now().date()

    queryset = Athlete.objects.select_related("sport").prefetch_related(
        "photos",
        "disciplines",
        "achievements",
        "upcoming_events",
        "sponsorship_assets",
    )

    if filters.search:
        queryset = queryset.filter(full_name__icontains=filters.search)

    if filters.sport_id:
        queryset = queryset.filter(sport_id=filters.sport_id)

    if filters.region:
        # Annotate with a boolean flag: does this athlete have at least one
        # upcoming event (today or later) whose location matches the region?
        # The Exists subquery is evaluated entirely in the database.
        has_regional_event = Exists(
            UpcomingEvent.objects.filter(
                athlete=OuterRef("pk"),
                start_date__gte=today,
                location__icontains=filters.region,
            )
        )
        queryset = queryset.annotate(has_regional_event=has_regional_event).order_by(
            "-has_regional_event", "full_name"
        )
    else:
        queryset = queryset.order_by("full_name")

    serializer = AthleteCardSerializer(queryset, many=True)
    data = serializer.data
    payload: dict = {
        "count": len(data),
        "results": data,
        "empty_state": len(data) == 0,
    }
    if not data:
        payload["message"] = "Aucun athlète n'est disponible pour le moment."
    return payload


def sport_list_payload() -> Iterable[dict]:
    """Return serialized sports for the public sports listing.

    Returns:
        Iterable[dict]: Ordered list of serialized Sport objects.
    """
    sports = Sport.objects.all().prefetch_related("disciplines").order_by("name")
    return SportSerializer(sports, many=True).data


def sport_disciplines_payload(sport_id: str) -> dict:
    """Return serialized data for a single sport and its disciplines.

    Args:
        sport_id (str): UUID of the requested sport.

    Returns:
        dict: Payload with ``sport`` and ``disciplines`` keys.

    Raises:
        django.http.Http404: When no sport matches ``sport_id``.
    """
    sport = get_object_or_404(
        Sport.objects.prefetch_related("disciplines"), pk=sport_id
    )
    disciplines = sport.disciplines.order_by("name")
    return {
        "sport": SportSerializer(sport, context={"include_disciplines": False}).data,
        "disciplines": SportDisciplineSerializer(disciplines, many=True).data,
    }


def athlete_photos_payload(athlete_id: str) -> dict:
    """Return the serialized gallery for the requested athlete.

    Args:
        athlete_id (str): UUID of the requested athlete.

    Returns:
        dict: Payload with ``athlete_id`` and ``photos`` keys.

    Raises:
        django.http.Http404: When no athlete matches ``athlete_id``.
    """
    athlete = get_object_or_404(
        Athlete.objects.prefetch_related("photos"),
        pk=athlete_id,
    )
    photos = athlete.photos.all()
    return {
        "athlete_id": str(athlete.id),
        "photos": AthletePhotoSerializer(photos, many=True).data,
    }
