"""Unit tests for the helper functions exposed in ``athletes.services``."""

from __future__ import annotations

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from athletes.models import Athlete, AthletePhoto, Sport, SportDiscipline
from athletes.services import (
    AthleteCardFilters,
    athlete_cards_payload,
    athlete_photos_payload,
    base_athlete_queryset,
    my_athletes_queryset,
    sport_disciplines_payload,
    sport_list_payload,
)
from users.models import AgentProfile


pytestmark = pytest.mark.django_db


def create_sport(name: str, *, emoji: str = "🏅") -> Sport:
    """Convenience helper to create a sport with a default discipline."""

    sport = Sport.objects.create(name=name, emoji=emoji)
    SportDiscipline.objects.create(sport=sport, name=f"{name} Discipline", slug=f"{name}-d")
    return sport


def create_athlete(*, agent: AgentProfile, sport: Sport, name: str) -> Athlete:
    """Create a minimal athlete bound to the provided agent and sport."""

    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent,
        full_name=name,
        birth_date=date(1990, 1, 1),
        nationality="FR",
    )
    return athlete


def test_base_athlete_queryset_returns_all(agent_user):
    """The base queryset should expose every athlete with related data loaded."""

    sport = create_sport("Basketball")
    athlete_one = create_athlete(agent=agent_user.agent_profile, sport=sport, name="Alice Player")
    athlete_two = create_athlete(agent=agent_user.agent_profile, sport=sport, name="Bob Player")

    queryset = base_athlete_queryset()

    assert set(queryset.values_list("id", flat=True)) == {athlete_one.id, athlete_two.id}


def test_my_athletes_queryset_filters_by_agent(agent_user, user_model):
    """Only athletes belonging to the provided agent profile should be returned."""

    sport = create_sport("Handball")
    mine = create_athlete(agent=agent_user.agent_profile, sport=sport, name="Home Athlete")

    other_user = user_model.objects.create_user(
        email="other-agent@example.com",
        password="pass1234",
        first_name="Other",
        last_name="Agent",
    )
    other_agent = AgentProfile.objects.create(user=other_user, display_name="Other Agent")
    create_athlete(agent=other_agent, sport=sport, name="Away Athlete")

    queryset = my_athletes_queryset(agent_user.agent_profile)

    assert list(queryset.values_list("id", flat=True)) == [mine.id]


def test_athlete_cards_payload_supports_filters(agent_user):
    """The payload builder applies the provided search and sport filters."""

    primary_sport = create_sport("Cycling")
    secondary_sport = create_sport("Swimming")
    create_athlete(agent=agent_user.agent_profile, sport=primary_sport, name="Clara Sprinter")
    create_athlete(agent=agent_user.agent_profile, sport=primary_sport, name="Adele Rider")
    target = create_athlete(agent=agent_user.agent_profile, sport=secondary_sport, name="Bella Diver")

    payload = athlete_cards_payload(AthleteCardFilters(search="Bella"))
    assert payload["count"] == 1
    assert payload["results"][0]["full_name"] == target.full_name
    assert payload["empty_state"] is False

    payload_by_sport = athlete_cards_payload(AthleteCardFilters(sport_id=str(primary_sport.id)))
    names = [item["full_name"] for item in payload_by_sport["results"]]
    assert names == ["Adele Rider", "Clara Sprinter"]


def test_athlete_cards_payload_empty_state_message():
    """When no athlete matches the filters the payload should expose the empty state."""

    payload = athlete_cards_payload(AthleteCardFilters(search="No match"))

    assert payload == {
        "count": 0,
        "results": [],
        "empty_state": True,
        "message": "Aucun athlète n'est disponible pour le moment.",
    }


def test_sport_list_payload_serializes_disciplines():
    """The sport listing should include all available disciplines ordered by name."""

    cycling = create_sport("Cycling")
    SportDiscipline.objects.create(
        sport=cycling,
        name="Track",
        slug="cycling-track",
    )
    running = create_sport("Running")

    payload = sport_list_payload()

    assert [item["name"] for item in payload] == ["Cycling", "Running"]
    cycling_payload = next(item for item in payload if item["id"] == str(cycling.id))
    discipline_names = [disc["name"] for disc in cycling_payload["disciplines"]]
    assert discipline_names == ["Cycling Discipline", "Track"]


def test_sport_disciplines_payload_returns_nested_data():
    """Fetching a sport by id should return the sport and its sorted disciplines."""

    sport = create_sport("Triathlon")
    SportDiscipline.objects.create(sport=sport, name="Swim", slug="tri-swim")
    SportDiscipline.objects.create(sport=sport, name="Bike", slug="tri-bike")

    payload = sport_disciplines_payload(str(sport.id))

    assert payload["sport"]["id"] == str(sport.id)
    assert "disciplines" not in payload["sport"]
    assert [d["name"] for d in payload["disciplines"]] == ["Bike", "Swim", "Triathlon Discipline"]


def test_athlete_photos_payload_returns_gallery(agent_user):
    """The photo payload should expose the gallery entries for the athlete."""

    sport = create_sport("Climbing")
    athlete = create_athlete(agent=agent_user.agent_profile, sport=sport, name="Gallery Star")

    image_file = SimpleUploadedFile("photo.png", b"fake image", content_type="image/png")
    photo = AthletePhoto.objects.create(athlete=athlete, image=image_file, caption="Lead Wall")

    payload = athlete_photos_payload(str(athlete.id))

    assert payload["athlete_id"] == str(athlete.id)
    assert [p["caption"] for p in payload["photos"]] == [photo.caption]
