"""Payment subscription cancellation scenarios."""

# These tests exercise permission gates enforced by the REST API to ensure
# billing entitlements align with configured plan features.

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_cancel_org_subscription_denied_without_feature(
    owner_user, organisations_setup
):
    """Organisation owners lacking management feature cannot cancel subscriptions.

    Args:
        owner_user (User): Authenticated organisation owner executing the call.
        organisations_setup (dict[str, Any]): Fixture providing organisation and
            subscription objects for the scenario.
    """

    client = APIClient()
    client.force_authenticate(user=owner_user)
    subscription = organisations_setup["organisation"].subscriptions.first()
    plan = subscription.plan
    plan.features["organisation_subscription_management"] = False
    plan.save(update_fields=["features"])

    url = reverse("payments-subscription-me")
    response = client.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "organisation_subscription_management"


@pytest.mark.django_db
def test_cancel_agent_subscription_requires_feature(agent_subscription):
    """Agent subscriptions require the management feature to cancel.

    Args:
        agent_subscription (Subscription): Existing subscription fixture scoped
            to an agent profile.
    """

    client = APIClient()
    agent = agent_subscription.agent.user
    client.force_authenticate(user=agent)

    plan = agent_subscription.plan
    plan.features["agent_subscription_management"] = False
    plan.save(update_fields=["features"])

    url = reverse("payments-subscription-me")
    response = client.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "agent_subscription_management"
