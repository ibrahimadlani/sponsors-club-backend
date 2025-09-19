"""Integration tests for notification endpoints."""

# pylint: disable=no-member

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture(name="notifications_client")
def fixture_notifications_client(owner_user):
    """Return an authenticated client for the owner user."""

    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.mark.django_db
def test_agent_notifications_require_feature(agent_user):
    """Agents without the notification center feature receive a denial."""

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("notifications-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "notification_center"


@pytest.mark.django_db
def test_agent_notifications_with_plan(agent_subscription):
    """Agents with notification access should fetch notifications successfully."""

    client = APIClient()
    agent = agent_subscription.agent.user
    client.force_authenticate(user=agent)
    url = reverse("notifications-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_collaborator_notifications_require_feature(
    notifications_client,
    organisations_setup,
):
    """Collaborator access is denied when the plan disables notifications."""

    organisation = organisations_setup["organisation"]
    subscription = organisation.subscriptions.first()
    plan = subscription.plan
    plan.features["notification_center"] = False
    plan.save(update_fields=["features"])

    url = reverse("notifications-list")
    response = notifications_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "notification_center"
