"""Messaging thread creation integration tests."""

from datetime import date

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import Athlete, Sport
from follows.models import Follow
from organisations.models import Collaborator


@pytest.fixture(name="thread_payload_data")
def fixture_thread_payload(agent_user, organisations_setup):
    """Return the canonical payload for creating a thread.

    Args:
        agent_user (User): Agent initiating the conversation.
        organisations_setup (dict): Fixture-provided collaborator bundle.

    Returns:
        dict: Payload containing the collaborator and agent identifiers.
    """

    collaborator = organisations_setup["collaborator"]
    return {
        "collaborator_id": str(collaborator.id),
        "agent_id": str(agent_user.agent_profile.id),
    }


@pytest.mark.django_db
def test_agent_without_subscription_cannot_create_thread(
    agent_user, thread_payload_data
):
    """Ensure agents without the messaging feature are denied access.

    Args:
        agent_user (User): Agent account lacking the subscription.
        thread_payload_data (dict): Baseline request payload.
    """

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("messaging-thread-list")
    response = client.post(url, thread_payload_data, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload["required_feature"] == "messaging_tier"
    assert "Pro+" in payload["detail"]


@pytest.mark.django_db
def test_agent_with_subscription_can_create_thread(
    agent_user,
    agent_subscription,
    thread_payload_data,
):
    """Verify agents with the feature can open new threads.

    Args:
        agent_user (User): Agent requesting the thread.
        agent_subscription (Subscription): Active plan enabling messaging.
        thread_payload_data (dict): Baseline request payload.
    """

    del agent_subscription

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("messaging-thread-list")
    response = client.post(url, thread_payload_data, format="json")
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_collaborator_can_create_thread(owner_user, agent_user):
    """Ensure collaborators can initiate threads.

    Args:
        owner_user (User): Organisation owner acting as collaborator.
        agent_user (User): Target agent for the conversation.
    """

    payload = {
        "agent_id": str(agent_user.agent_profile.id),
    }
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse("messaging-thread-list")
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert Collaborator.objects.filter(user=owner_user).exists()


@pytest.mark.django_db
def test_collaborator_cannot_create_thread_without_follow(owner_user, agent_user):
    """Collaborators must follow the athlete before opening a thread."""

    sport = Sport.objects.create(name="Basketball")
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Jordan Example",
        birth_date=date(1990, 1, 1),
        nationality="FR",
    )
    payload = {
        "agent_id": str(agent_user.agent_profile.id),
        "athlete_id": str(athlete.id),
    }
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse("messaging-thread-list")
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "athlete_id" in response.json()


@pytest.mark.django_db
def test_collaborator_can_create_thread_when_following(owner_user, agent_user):
    """Collaborators who follow the athlete can open a thread."""

    sport = Sport.objects.create(name="Handball")
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Alex Followed",
        birth_date=date(1995, 5, 5),
        nationality="FR",
    )
    collaborator = Collaborator.objects.filter(user=owner_user).first()
    assert collaborator is not None
    Follow.objects.create(collaborator=collaborator, athlete=athlete)

    payload = {
        "agent_id": str(agent_user.agent_profile.id),
        "athlete_id": str(athlete.id),
    }
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse("messaging-thread-list")
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
