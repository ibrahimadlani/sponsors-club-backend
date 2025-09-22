"""Tests for message read state updates."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from messaging.models import Message, Thread


@pytest.fixture
def message_setup(agent_user, organisations_setup):
    """Create a thread and a message sent by the collaborator.

    Args:
        agent_user (User): Agent receiving the message.
        organisations_setup (dict): Fixture bundle containing the collaborator.

    Returns:
        dict: Convenience object holding the thread, message, and collaborator.
    """

    collaborator = organisations_setup["collaborator"]
    thread = Thread.objects.create(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )
    message = Message.objects.create(
        thread=thread,
        sender=collaborator.user,
        content="Hello agent!",
    )
    return {
        "thread": thread,
        "message": message,
        "collaborator": collaborator,
    }


@pytest.mark.django_db
def test_recipient_can_mark_message_as_read(message_setup, agent_user):
    """Assert the recipient may mark a message as read.

    Args:
        message_setup (dict): Fixture containing the thread data.
        agent_user (User): Agent acting as the message recipient.
    """

    message = message_setup["message"]
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("message-read", args=[message.id])

    response = client.patch(url, {"is_read": True}, format="json")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["is_read"] is True
    message.refresh_from_db()
    assert message.is_read is True


@pytest.mark.django_db
def test_sender_cannot_mark_message_as_read(message_setup):
    """Ensure the author cannot toggle the read flag.

    Args:
        message_setup (dict): Fixture containing the thread data.
    """

    message = message_setup["message"]
    collaborator = message_setup["collaborator"]
    client = APIClient()
    client.force_authenticate(user=collaborator.user)
    url = reverse("message-read", args=[message.id])

    response = client.patch(url, {"is_read": True}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload["detail"] == "Only the message recipient may update read status."
    message.refresh_from_db()
    assert message.is_read is False
