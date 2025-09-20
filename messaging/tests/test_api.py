"""Unit and integration tests for messaging serializers and REST endpoints."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from messaging.models import Message, Thread
from messaging.serializers import MessageSerializer, ThreadSerializer


@pytest.mark.django_db
def test_message_serializer_create_updates_thread_timestamp(
    owner_user, agent_user, organisations_setup
):
    """Creating a message should persist sender and update last_message_at."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator, agent=agent_user.agent_profile
    )
    factory = APIRequestFactory()
    request = factory.post(
        "/api/threads/%s/messages/" % thread.id, {"content": "Hello"}
    )
    request.user = owner_user

    serializer = MessageSerializer(
        data={"content": "Hello"},
        context={"request": request, "thread": thread},
    )
    assert serializer.is_valid(), serializer.errors
    message = serializer.save()

    thread.refresh_from_db()
    assert message.sender == owner_user
    assert message.thread == thread
    assert thread.last_message_at == message.created_at
    representation = MessageSerializer(message, context={"request": request}).data
    assert representation["attachment"] is None


@pytest.mark.django_db
def test_thread_serializer_includes_last_message(
    owner_user, agent_user, organisations_setup
):
    """Thread serializer should return participant summaries and recent message."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator, agent=agent_user.agent_profile
    )
    message = Message.objects.create(thread=thread, sender=owner_user, content="Latest")

    factory = APIRequestFactory()
    request = factory.get("/api/threads/")
    serializer = ThreadSerializer(thread, context={"request": request})
    data = serializer.data

    assert data["collaborator"]["id"] == str(collaborator.id)
    assert data["agent"]["id"] == str(agent_user.agent_profile.id)
    assert data["last_message"]["id"] == str(message.id)
    assert data["last_message"]["content"] == "Latest"


@pytest.mark.django_db
def test_thread_list_returns_user_threads(
    api_client, owner_user, agent_user, organisations_setup
):
    """Listing threads should return only those involving the authenticated user."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator, agent=agent_user.agent_profile
    )
    Message.objects.create(thread=thread, sender=owner_user, content="Hi")

    api_client.force_authenticate(owner_user)
    url = reverse("messaging:thread-list")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["id"] == str(thread.id)
    assert payload[0]["last_message"]["content"] == "Hi"


@pytest.mark.django_db
def test_thread_messages_endpoints(
    api_client, owner_user, agent_user, organisations_setup
):
    """Thread message listing and creation behave as expected."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator, agent=agent_user.agent_profile
    )
    Message.objects.create(thread=thread, sender=agent_user, content="Welcome")

    api_client.force_authenticate(owner_user)
    list_url = reverse("messaging:thread-messages", kwargs={"thread_id": thread.id})
    response = api_client.get(list_url)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["content"] == "Welcome"

    create_response = api_client.post(list_url, {"content": "Reply"}, format="json")
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    assert created["content"] == "Reply"
    thread.refresh_from_db()
    assert Message.objects.filter(thread=thread).count() == 2
    assert thread.last_message_at is not None


@pytest.mark.django_db
def test_mark_message_as_read(api_client, owner_user, agent_user, organisations_setup):
    """POSTing to the read endpoint should toggle the flag for the thread participant."""

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator, agent=agent_user.agent_profile
    )
    message = Message.objects.create(thread=thread, sender=agent_user, content="Ping")

    api_client.force_authenticate(owner_user)
    url = reverse("messaging:message-read", kwargs={"message_id": message.id})
    response = api_client.post(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["is_read"] is True
    message.refresh_from_db()
    assert message.is_read is True
