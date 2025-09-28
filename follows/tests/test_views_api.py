"""Tests covering the follows API views end to end."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import Athlete, Sport, SportDiscipline
from follows.models import Follow
from follows.views import AthleteFollowView
from organisations.models import Collaborator, Organisation


@pytest.fixture
def follow_api_client(owner_user) -> APIClient:
    """Return an authenticated API client for follow interactions."""

    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def create_follow_athlete(agent_user):
    """Factory generating persisted athletes for follow scenarios."""

    def _create(full_name: str | None = None) -> Athlete:
        sport = Sport.objects.create(
            name=f"Follow Sport {uuid4().hex}",
            category=Sport.Category.INDIVIDUAL,
        )
        discipline = SportDiscipline.objects.create(
            sport=sport,
            name=f"Discipline {uuid4().hex[:6]}",
            description="Primary discipline",
        )
        athlete = Athlete.objects.create(
            sport=sport,
            agent=agent_user.agent_profile,
            full_name=full_name or f"Follow Athlete {uuid4().hex[:6]}",
            birth_date=date(1990, 1, 1),
            nationality="FR",
        )
        athlete.disciplines.add(discipline)
        return athlete

    return _create


@pytest.mark.django_db
def test_follow_creation_infers_collaborator_when_missing_identifier(
    follow_api_client,
    organisations_setup,
    create_follow_athlete,
):
    """The view falls back to the user's collaborator when none is provided."""

    athlete = create_follow_athlete()
    url = reverse("athlete-follow", kwargs={"athlete_id": athlete.id})

    response = follow_api_client.post(url, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert Follow.objects.filter(
        collaborator=organisations_setup["collaborator"],
        athlete=athlete,
    ).exists()


@pytest.mark.django_db
def test_follow_creation_returns_existing_relationship(
    follow_api_client,
    organisations_setup,
    create_follow_athlete,
):
    """Submitting the same follow twice reuses the existing relationship."""

    collaborator = organisations_setup["collaborator"]
    athlete = create_follow_athlete()
    Follow.objects.create(collaborator=collaborator, athlete=athlete)

    url = reverse("athlete-follow", kwargs={"athlete_id": athlete.id})
    response = follow_api_client.post(
        url,
        {"collaborator_id": str(collaborator.id)},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_follow_creation_requires_collaborator_membership(
    agent_user, create_follow_athlete
):
    """Requests from users without collaborator membership are rejected."""

    view = AthleteFollowView()
    request = SimpleNamespace(data={}, query_params={}, user=agent_user)

    response = view.post(request, athlete_id=create_follow_athlete().id)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"detail": "Collaborator membership required."}


@pytest.mark.django_db
def test_follow_limit_denied_when_plan_has_no_available_slots(
    monkeypatch,
    owner_user,
    organisations_setup,
):
    """Invalid or zero slot allocations surface the requirement denial payload."""

    collaborator = organisations_setup["collaborator"]
    view = AthleteFollowView()
    request = SimpleNamespace(data={}, query_params={}, user=owner_user)

    monkeypatch.setattr(
        "follows.views.get_collaborator_plan_features",
        lambda _user, _organisation: {"max_follows": "not-a-number"},
    )
    monkeypatch.setattr(
        "follows.views.user_feature_requirement",
        lambda _user, _feature: (None, False),
    )

    response = view._enforce_follow_limits(request, collaborator)

    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["required_feature"] == "max_follows"
    assert "Follow limit reached" in response.data["detail"]


@pytest.mark.django_db
def test_follow_deletion_uses_query_parameter_for_collaborator_lookup(
    follow_api_client,
    organisations_setup,
    create_follow_athlete,
):
    """Deletion resolves the collaborator from query parameters when provided."""

    collaborator = organisations_setup["collaborator"]
    athlete = create_follow_athlete()
    Follow.objects.create(collaborator=collaborator, athlete=athlete)

    url = reverse("athlete-follow", kwargs={"athlete_id": athlete.id})
    response = follow_api_client.delete(
        f"{url}?collaborator_id={collaborator.id}",
        format="json",
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Follow.objects.filter(
        collaborator=collaborator, athlete=athlete
    ).exists()


@pytest.mark.django_db
def test_follow_deletion_returns_not_found_when_missing(
    follow_api_client, create_follow_athlete
):
    """Attempting to unfollow a missing relationship yields a 404 response."""

    url = reverse("athlete-follow", kwargs={"athlete_id": create_follow_athlete().id})

    response = follow_api_client.delete(url, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data == {"detail": "Follow relationship not found."}


@pytest.mark.django_db
def test_my_follows_lists_all_athletes_across_collaborations(
    follow_api_client,
    owner_user,
    organisations_setup,
    create_follow_athlete,
):
    """The listing aggregates follows from every collaborator linked to the user."""

    collaborator = organisations_setup["collaborator"]
    first_follow = Follow.objects.create(
        collaborator=collaborator, athlete=create_follow_athlete()
    )

    organisation = Organisation.objects.create(
        owner=owner_user,
        name="Expansion Org",
        type=Organisation.Type.BRAND,
    )
    secondary_collaborator = Collaborator.objects.create(
        user=owner_user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Marketing Lead",
    )
    second_follow = Follow.objects.create(
        collaborator=secondary_collaborator, athlete=create_follow_athlete()
    )

    response = follow_api_client.get(reverse("my-follows"))

    assert response.status_code == status.HTTP_200_OK
    athlete_ids = {item["athlete"]["id"] for item in response.json()}
    assert athlete_ids == {str(first_follow.athlete_id), str(second_follow.athlete_id)}
