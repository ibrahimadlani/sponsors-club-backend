"""Notification access control checks.

The suite focuses on the feature-gating logic enforced by the API views to
ensure the notification center only appears for eligible users.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture(name="notifications_client")
def fixture_notifications_client(owner_user):
    """Return an authenticated client for the owner user.

    Args:
        owner_user (users.models.User): Organisation owner seeded via a global
            fixture.

    Returns:
        rest_framework.test.APIClient: Client authenticated as the owner to
        exercise notification endpoints.
    """

    client = APIClient()
    client.force_authenticate(user=owner_user)
    # The returned client keeps authentication headers so each test can perform
    # multiple calls without re-logging in.
    return client


@pytest.mark.django_db
def test_agent_notifications_require_feature(agent_user):
    """Agents without the notification center feature receive a denial.

    Args:
        agent_user (users.models.User): Agent whose organisation lacks the
            ``notification_center`` feature flag.
    """

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("notifications-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "notification_center"


@pytest.mark.django_db
def test_agent_notifications_with_plan(agent_subscription):
    """Agents with notification access fetch notifications successfully.

    Args:
        agent_subscription (organisations.models.Subscription): Subscription
            fixture that already includes the notification center feature.
    """

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
    """Collaborator access is denied when the plan disables notifications.

    Args:
        notifications_client (rest_framework.test.APIClient): Pre-authenticated
            client for the organisation owner.
        organisations_setup (dict): Fixture that returns the seeded
            organisation, plan, and related associations.
    """

    organisation = organisations_setup["organisation"]
    subscription = organisation.subscriptions.first()
    plan = subscription.plan
    plan.features["notification_center"] = False
    plan.save(update_fields=["features"])

    url = reverse("notifications-list")
    response = notifications_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "notification_center"
