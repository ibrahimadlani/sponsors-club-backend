# pylint: skip-file

from datetime import date

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from analytics.models import AthleteStat
from athletes.models import Athlete, Sport


@pytest.fixture
def stats_sport():
    return Sport.objects.create(name="Volley", discipline="Team Sport")


@pytest.fixture
def stats_athlete(agent_user, stats_sport):
    return Athlete.objects.create(
        sport=stats_sport,
        agent=agent_user.agent_profile,
        full_name="Stat Athlete",
        birth_date=date(1995, 5, 5),
        nationality="FR",
    )


@pytest.fixture
def athlete_stat(stats_athlete):
    return AthleteStat.objects.create(
        athlete=stats_athlete,
        metric=AthleteStat.Metric.FOLLOWERS,
        value=1000,
        date=date.today(),
        extra={},
    )


@pytest.mark.django_db
def test_agent_can_view_own_stats(agent_user, stats_athlete, athlete_stat):
    """Ensure an authenticated agent receives a 200 response containing the
    freshly-recorded metric for their own athlete, proving ownership-based
    access is respected."""

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-stats", kwargs={"athlete_id": stats_athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["metric"] == AthleteStat.Metric.FOLLOWERS


@pytest.mark.django_db
def test_collaborator_without_subscription_denied(
    owner_user,
    stats_athlete,
    athlete_stat,
    organisations_setup,
):
    """Assert that a collaborator without the premium stats entitlement is
    blocked with a 403 and receives the standard upgrade guidance payload
    so the UI can surface upgrade messaging."""

    client = APIClient()
    client.force_authenticate(user=owner_user)
    subscription = organisations_setup["organisation"].subscriptions.first()
    plan = subscription.plan
    plan.features["athlete_stats_scope"] = None
    plan.save(update_fields=["features"])
    url = reverse("athlete-stats", kwargs={"athlete_id": stats_athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload["required_feature"] == "athlete_stats_scope"
    assert payload["recommended_plans"]


@pytest.mark.django_db
def test_collaborator_with_subscription_can_view(
    owner_user,
    organisation_subscription,
    stats_athlete,
    athlete_stat,
):
    """Validate that collaborators covered by an active subscription can
    fetch athlete stats successfully, confirming the entitlement gate is
    transparent for eligible workspaces."""

    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse("athlete-stats", kwargs={"athlete_id": stats_athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["metric"] == AthleteStat.Metric.FOLLOWERS
