"""Integration tests for the messaging REST API."""

from __future__ import annotations

import pytest
from messaging.models import Message, Thread


@pytest.mark.django_db
def test_thread_list_returns_threads_for_participant(api_client, agent_user, organisations_setup):
    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(collaborator=collaborator, agent=agent_user.agent_profile)
    message = Message.objects.create(thread=thread, sender=agent_user, content="Hello")
    Thread.objects.filter(id=thread.id).update(last_message_at=message.created_at)

    api_client.force_authenticate(user=collaborator.user)
    url = "/api/messaging/threads/"
    response = api_client.get(url)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["id"] == str(thread.id)
    assert result["last_message"]["id"] == str(message.id)
    assert result["last_message"]["content"] == "Hello"


@pytest.mark.django_db
def test_send_message_updates_last_message_at(api_client, agent_user, organisations_setup):
    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(collaborator=collaborator, agent=agent_user.agent_profile)

    api_client.force_authenticate(user=collaborator.user)
    url = f"/api/messaging/threads/{thread.id}/messages/"
    response = api_client.post(url, {"content": "Hi there"}, format="json")

    assert response.status_code == 201
    thread.refresh_from_db()
    message = Message.objects.get(thread=thread)
    assert thread.last_message_at == message.created_at
    assert response.data["id"] == str(message.id)
    assert message.sender_id == collaborator.user_id


@pytest.mark.django_db
def test_mark_message_read(api_client, agent_user, organisations_setup):
    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(collaborator=collaborator, agent=agent_user.agent_profile)
    message = Message.objects.create(thread=thread, sender=agent_user, content="Ping")

    api_client.force_authenticate(user=collaborator.user)
    url = f"/api/messaging/messages/{message.id}/read/"
    response = api_client.post(url)

    assert response.status_code == 200
    message.refresh_from_db()
    assert message.is_read is True
    assert response.data["is_read"] is True
