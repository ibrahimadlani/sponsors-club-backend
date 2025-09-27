"""API tests covering the messaging view layer."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from messaging.models import Message, Thread
from users.models import AgentProfile


@pytest.mark.django_db
def test_thread_list_returns_threads_for_agent(
    api_client, agent_user, organisations_setup, user_model
):
    """Agents should only see threads where they participate."""

    collaborator = organisations_setup["collaborator"]
    other_collaborator_user = user_model.objects.create_user(
        email="other-collab@test.com",
        password="pass1234",
        first_name="Other",
        last_name="Collaborator",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    other_collaborator = collaborator.__class__.objects.create(
        user=other_collaborator_user,
        organisation=collaborator.organisation,
        role=collaborator.__class__.Role.MEMBER,
        job_title="Marketer",
    )

    recent_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
        last_message_at=timezone.now(),
    )
    older_thread = Thread.objects.create(
        collaborator=other_collaborator,
        agent=agent_user.agent_profile,
        last_message_at=timezone.now() - timedelta(hours=1),
    )
    outsider_user = user_model.objects.create_user(
        email="outsider-agent@test.com",
        password="pass1234",
        first_name="Outside",
        last_name="Agent",
        account_type=user_model.AccountType.AGENT,
    )
    outsider_profile = AgentProfile.objects.create(
        user=outsider_user,
        display_name="Other Agent",
    )
    Thread.objects.create(
        collaborator=other_collaborator,
        agent=outsider_profile,
    )

    api_client.force_authenticate(user=agent_user)
    url = reverse("messaging-thread-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    ids = [item["id"] for item in payload["results"]]
    assert ids == [str(recent_thread.id), str(older_thread.id)]


@pytest.mark.django_db
def test_thread_list_returns_threads_for_collaborator(
    api_client, organisations_setup, agent_user, user_model
):
    """Collaborators should only receive their own conversations."""

    collaborator = organisations_setup["collaborator"]
    owner = organisations_setup["owner"]

    primary_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
        last_message_at=timezone.now(),
    )

    other_agent_user = user_model.objects.create_user(
        email="other-agent@test.com",
        password="pass1234",
        first_name="Second",
        last_name="Agent",
        account_type=user_model.AccountType.AGENT,
    )
    other_agent_profile = AgentProfile.objects.create(
        user=other_agent_user,
        display_name="Agent Two",
    )
    secondary_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=other_agent_profile,
    )

    api_client.force_authenticate(user=owner)
    url = reverse("messaging-thread-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    ids = [item["id"] for item in payload["results"]]
    assert ids[0] == str(primary_thread.id)
    assert set(ids) == {str(primary_thread.id), str(secondary_thread.id)}


@pytest.mark.django_db
def test_thread_create_rejects_unaffiliated_request(
    api_client, agent_user, organisations_setup, user_model, monkeypatch
):
    """Users without a direct role or staff status are rejected."""

    outsider = user_model.objects.create_user(
        email="random@test.com",
        password="pass1234",
        first_name="Random",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    collaborator = organisations_setup["collaborator"]
    payload = {
        "collaborator_id": str(collaborator.id),
        "agent_id": str(agent_user.agent_profile.id),
    }

    class DummySerializer:
        def __init__(self, data, context):
            assert data == payload
            self.validated_data = {
                "agent": agent_user.agent_profile,
                "collaborator": collaborator,
                "athlete": None,
            }

        def is_valid(self, raise_exception):  # pragma: no cover - behaviour trivial
            return True

        def save(self):  # pragma: no cover - should never be called
            raise AssertionError("Serializer.save() should not be invoked")

    monkeypatch.setattr("messaging.views.ThreadCreateSerializer", DummySerializer)

    api_client.force_authenticate(user=outsider)
    url = reverse("messaging-thread-list")
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Permission denied."


@pytest.mark.django_db
def test_thread_messages_view_get_returns_paginated_messages(
    api_client, agent_user, organisations_setup
):
    """Participants can retrieve thread messages with pagination metadata."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )
    first_message = Message.objects.create(
        thread=thread,
        sender=collaborator.user,
        content="Hello",
    )
    second_message = Message.objects.create(
        thread=thread,
        sender=collaborator.user,
        content="There",
    )

    api_client.force_authenticate(user=agent_user)
    url = reverse("thread-messages", args=[thread.id])
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["count"] == 2
    contents = [item["content"] for item in payload["results"]]
    assert contents == [first_message.content, second_message.content]


@pytest.mark.django_db
def test_thread_messages_view_get_denies_non_participant(
    api_client, agent_user, organisations_setup, user_model
):
    """Access is denied when the user does not participate in the thread."""

    collaborator = organisations_setup["collaborator"]
    other_agent_user = user_model.objects.create_user(
        email="other-agent-list@test.com",
        password="pass1234",
        first_name="Other",
        last_name="Agent",
        account_type=user_model.AccountType.AGENT,
    )
    other_agent_profile = AgentProfile.objects.create(
        user=other_agent_user,
        display_name="Agent Three",
    )
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=other_agent_profile,
    )

    api_client.force_authenticate(user=agent_user)
    url = reverse("thread-messages", args=[thread.id])
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Thread not found or access denied."


@pytest.mark.django_db
def test_thread_messages_view_post_creates_message(
    api_client, organisations_setup, agent_user
):
    """Participants can post a new message within a thread."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )

    api_client.force_authenticate(user=collaborator.user)
    url = reverse("thread-messages", args=[thread.id])
    response = api_client.post(url, {"content": "New message"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["content"] == "New message"
    assert Message.objects.filter(thread=thread).count() == 1


@pytest.mark.django_db
def test_thread_messages_view_post_denies_non_participant(
    api_client, agent_user, organisations_setup, user_model
):
    """Posting is rejected when the user is outside the thread."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )
    outsider = user_model.objects.create_user(
        email="intruder@test.com",
        password="pass1234",
        first_name="Intruder",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )

    api_client.force_authenticate(user=outsider)
    url = reverse("thread-messages", args=[thread.id])
    response = api_client.post(url, {"content": "Should fail"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Thread not found or access denied."
