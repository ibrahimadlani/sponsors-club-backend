"""Thread list API regression tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from django.urls import reverse
from rest_framework import status

from messaging.models import Thread
from organisations.models import Collaborator, Organisation
from users.models import AgentProfile


def _response_thread_ids(payload: dict) -> list[UUID]:
    """Extract the thread identifiers from a paginated API payload."""

    return [UUID(item["id"]) for item in payload.get("results", [])]


@pytest.mark.django_db
def test_thread_list_returns_threads_for_agent(
    api_client,
    agent_user,
    agent_subscription,
    organisations_setup,
    user_model,
):
    """An agent should only see threads that involve their account."""

    del agent_subscription

    collaborator = organisations_setup["collaborator"]
    agent_profile = agent_user.agent_profile

    visible_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_profile,
    )

    other_agent = user_model.objects.create_user(
        email="second-agent@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    AgentProfile.objects.create(user=other_agent, display_name="Second Agent")
    second_owner = user_model.objects.create_user(
        email="second-owner@test.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    other_collaborator = Collaborator.objects.create(
        user=second_owner,
        organisation=organisations_setup["organisation"],
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    Thread.objects.create(
        collaborator=other_collaborator,
        agent=other_agent.agent_profile,
    )

    api_client.force_authenticate(user=agent_user)
    response = api_client.get(reverse("messaging-thread-list"))

    assert response.status_code == status.HTTP_200_OK
    assert _response_thread_ids(response.json()) == [visible_thread.id]


@pytest.mark.django_db
def test_thread_list_returns_threads_for_collaborator(
    api_client,
    owner_user,
    organisations_setup,
    user_model,
):
    """A collaborator should only see the threads tied to their membership."""

    collaborator = organisations_setup["collaborator"]

    other_org = Organisation.objects.create(
        owner=owner_user,
        name="Other Org",
        sector="Media",
        size=Organisation.Size.SMALL,
        budget_min=Decimal("100.00"),
        budget_max=Decimal("200.00"),
        country="FR",
    )
    other_collaborator = Collaborator.objects.create(
        user=owner_user,
        organisation=other_org,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    other_agent = user_model.objects.create_user(
        email="agent-unrelated@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    AgentProfile.objects.create(user=other_agent, display_name="Unrelated Agent")
    other_thread = Thread.objects.create(
        collaborator=other_collaborator,
        agent=other_agent.agent_profile,
    )

    agent_user = user_model.objects.create_user(
        email="agent-thread@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    AgentProfile.objects.create(user=agent_user, display_name="Thread Agent")
    visible_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )

    api_client.force_authenticate(user=owner_user)
    response = api_client.get(reverse("messaging-thread-list"))

    assert response.status_code == status.HTTP_200_OK
    assert _response_thread_ids(response.json()) == [visible_thread.id, other_thread.id]
