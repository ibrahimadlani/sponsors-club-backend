"""API tests covering the messaging view layer."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from athletes.models import Athlete, Sport
from messaging.models import Message, Thread
from organisations.models import Organisation
from users.models import AgentProfile


@pytest.mark.django_db
def test_thread_list_returns_threads_for_agent(
    api_client, agent_user, organisations_setup, user_model
):
    """Agents should only see threads where they participate."""

    collaborator = organisations_setup["collaborator"]
    other_owner_user = user_model.objects.create_user(
        email="other-owner@test.com",
        password="pass1234",
        first_name="Other",
        last_name="Owner",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    other_organisation = Organisation.objects.create(
        # Owner now expects Collaborator; create organisation first then link via collaborator
        owner=None,
        name="Second Org",
        type=collaborator.organisation.type,
        industry="Tech",
        description="Another organisation",
        website_url="https://second.org",
        email_contact="contact@second.org",
        phone_contact="+33102030406",
        address_city="Lyon",
        address_country="FR",
        address_postal_code="69000",
        social_links={"linkedin": "https://linkedin.com/company/second-org"},
        founded_year=2015,
        employees_count=10,
        budget_range="5k-20k",
        sponsoring_focus=["sports individuels"],
    )
    other_collaborator = collaborator.__class__.objects.create(
        user=other_owner_user,
        organisation=other_organisation,
        role=collaborator.__class__.Role.OWNER,
        job_title="Founder",
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
    Message.objects.create(
        thread=recent_thread,
        sender=collaborator.user,
        content="Hello agent",
        is_read=False,
    )
    Message.objects.create(
        thread=recent_thread,
        sender=agent_user,
        content="Agent sent but should not count",
        is_read=False,
    )
    Message.objects.create(
        thread=older_thread,
        sender=other_collaborator.user,
        content="Older hello",
        is_read=False,
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

    first_thread = payload["results"][0]
    collaborator_payload = first_thread["collaborator"]
    assert collaborator_payload["first_name"] == collaborator.user.first_name
    assert collaborator_payload["last_name"] == collaborator.user.last_name
    assert collaborator_payload["organisation_name"] == collaborator.organisation.name
    assert collaborator_payload["avatar"] is None

    agent_payload = first_thread["agent"]
    assert agent_payload["id"] == str(agent_user.agent_profile.id)
    assert agent_payload["avatar"] is None
    assert first_thread["subtitle"] is None
    assert first_thread["avatar_badge_emoji"] is None
    assert first_thread["unread_messages_count"] == 1
    assert payload["unread_messages_total"] == 2


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
    )
    secondary_thread = Thread.objects.create(
        collaborator=collaborator,
        agent=other_agent_profile,
    )
    Message.objects.create(
        thread=primary_thread,
        sender=agent_user,
        content="Primary unread message",
        is_read=False,
    )
    Message.objects.create(
        thread=secondary_thread,
        sender=other_agent_profile.user,
        content="Secondary unread message",
        is_read=False,
    )
    Message.objects.create(
        thread=primary_thread,
        sender=owner,
        content="Collaborator sent but should not count",
        is_read=False,
    )

    api_client.force_authenticate(user=owner)
    url = reverse("messaging-thread-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    ids = [item["id"] for item in payload["results"]]
    assert ids[0] == str(primary_thread.id)
    assert set(ids) == {str(primary_thread.id), str(secondary_thread.id)}

    first_thread = payload["results"][0]
    assert first_thread["subtitle"] == f"Représenté par {agent_user.agent_profile.name}"
    assert first_thread["avatar_badge_emoji"] is None
    assert first_thread["unread_messages_count"] == 1
    assert payload["unread_messages_total"] == 2


@pytest.mark.django_db
def test_thread_list_includes_athlete_and_sport_metadata(
    api_client, organisations_setup, agent_user
):
    """Thread listings expose athlete avatar and sport metadata when linked."""

    collaborator = organisations_setup["collaborator"]
    sport = Sport.objects.create(name="Football", emoji="⚽")
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Elite Player",
        birth_date=date(2000, 1, 1),
        nationality="FR",
    )
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
        athlete=athlete,
        last_message_at=timezone.now(),
    )
    Message.objects.create(
        thread=thread,
        sender=collaborator.user,
        content="Hello sport",
        is_read=True,
    )

    api_client.force_authenticate(user=agent_user)
    url = reverse("messaging-thread-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    result = payload["results"][0]
    athlete_payload = result["athlete"]
    assert athlete_payload["id"] == str(athlete.id)
    assert athlete_payload["sport_id"] == str(sport.id)
    assert athlete_payload["sport_name"] == sport.name
    assert athlete_payload["sport_emoji"] == sport.emoji
    assert athlete_payload["avatar"] is None
    assert result["avatar_badge_emoji"] == sport.emoji
    assert result["subtitle"] is None
    assert result["unread_messages_count"] == 0
    assert payload["unread_messages_total"] == 0


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
