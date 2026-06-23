"""Tests covering follow entitlement and limit behaviours."""

from datetime import date

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import Athlete, Sport, SportDiscipline
from follows.models import Follow


@pytest.fixture(name="follow_client")
def fixture_follow_client(owner_user):
    """Return an authenticated API client for follow interactions.

    Args:
        owner_user: Fixture providing the organisation owner used for
            authentication.

    Returns:
        APIClient: Authenticated client ready to call follow endpoints.
    """

    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture(name="follow_athlete")
def fixture_follow_athlete(agent_user):
    """Create an athlete linked to the agent fixture for follow scenarios.

    Args:
        agent_user: Fixture representing the agent responsible for the new
            athlete.

    Returns:
        Athlete: Persisted athlete ready to be followed in tests.
    """

    sport = Sport.objects.create(
        name="Follow Sport", category=Sport.Category.INDIVIDUAL
    )
    SportDiscipline.objects.create(
        sport=sport,
        name="Individual Competition",
        description="Solo discipline",
    )
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Follow Athlete",
        birth_date=date(1990, 1, 1),
        nationality="FR",
    )
    discipline = SportDiscipline.objects.create(
        sport=sport,
        name="Solo Event",
        description="Default discipline",
    )
    athlete.disciplines.add(discipline)
    return athlete


@pytest.mark.django_db
def test_follow_limit_enforced(follow_client, organisations_setup, follow_athlete):
    """Reject follow creation when the organisation has reached its limit.

    Args:
        follow_client: Authenticated test client.
        organisations_setup: Fixture returning collaborator and subscription
            objects configured for the organisation.
        follow_athlete: Athlete that will be followed within the test.
    """

    collaborator = organisations_setup["collaborator"]
    subscription = organisations_setup["subscription"]
    plan = subscription.plan
    plan.features["max_follows"] = 1
    plan.save(update_fields=["features"])

    Follow.objects.create(collaborator=collaborator, athlete=follow_athlete)

    url = reverse("athlete-follow", kwargs={"athlete_id": follow_athlete.id})
    response = follow_client.post(
        url,
        {"collaborator_id": str(collaborator.id)},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "max_follows"


@pytest.mark.django_db
def test_follow_success_within_limit(
    follow_client, organisations_setup, follow_athlete
):
    """Allow follow creation when the organisation is under the limit.

    Args:
        follow_client: Authenticated test client.
        organisations_setup: Fixture returning collaborator and subscription
            objects configured for the organisation.
        follow_athlete: Athlete that will be followed within the test.
    """

    collaborator = organisations_setup["collaborator"]
    url = reverse("athlete-follow", kwargs={"athlete_id": follow_athlete.id})
    response = follow_client.post(
        url,
        {"collaborator_id": str(collaborator.id)},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_follow_requires_feature_when_zero_slots(
    follow_client,
    organisations_setup,
    follow_athlete,
):
    """Require an upgrade when the plan grants zero follow slots.

    Args:
        follow_client: Authenticated test client.
        organisations_setup: Fixture returning collaborator and subscription
            objects configured for the organisation.
        follow_athlete: Athlete that will be followed within the test.
    """

    subscription = organisations_setup["subscription"]
    plan = subscription.plan
    plan.features["max_follows"] = 0
    plan.save(update_fields=["features"])

    collaborator = organisations_setup["collaborator"]
    url = reverse("athlete-follow", kwargs={"athlete_id": follow_athlete.id})
    response = follow_client.post(
        url,
        {"collaborator_id": str(collaborator.id)},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "max_follows"
