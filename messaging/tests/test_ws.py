"""Websocket integration tests for the thread consumer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from core.asgi import application
from messaging.models import Message, Thread
from organisations.models import Collaborator, Organisation


async def _create_thread(agent_user, user_model) -> tuple[Thread, Any]:
    owner = await database_sync_to_async(user_model.objects.create_user)(
        email="collaborator@test.com",
        password="pass1234",
        first_name="Col",
        last_name="Laborator",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = await database_sync_to_async(Organisation.objects.create)(
        owner=owner,
        name="Realtime Org",
        sector="Sports",
        size=Organisation.Size.MEDIUM,
        budget_min=Decimal("1000"),
        budget_max=Decimal("5000"),
        country="FR",
    )
    collaborator = await database_sync_to_async(Collaborator.objects.create)(
        user=owner,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    thread = await database_sync_to_async(Thread.objects.create)(
        collaborator=collaborator,
        agent=agent_user.agent_profile,
    )
    return thread, owner


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_thread_consumer_delivers_messages(agent_user, user_model):
    """Participants should receive their own messages over the websocket connection."""

    thread, owner = await _create_thread(agent_user, user_model)
    token = str(AccessToken.for_user(owner))

    communicator = WebsocketCommunicator(application, f"/ws/threads/{thread.id}/")
    communicator.scope["headers"] = [(b"authorization", f"Bearer {token}".encode())]

    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"content": "Real-time hello"})
    response = await communicator.receive_json_from()
    assert response["content"] == "Real-time hello"
    assert response["sender"] == str(owner.id)
    assert response["thread"] == str(thread.id)

    count = await database_sync_to_async(Message.objects.filter(thread=thread).count)()
    assert count == 1

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_thread_consumer_rejects_non_participants(agent_user, user_model):
    """Connecting with a user that is not part of the thread should fail."""

    thread, _ = await _create_thread(agent_user, user_model)
    outsider = await database_sync_to_async(user_model.objects.create_user)(
        email="outsider@test.com",
        password="pass1234",
        first_name="Out",
        last_name="Sider",
    )
    token = str(AccessToken.for_user(outsider))

    communicator = WebsocketCommunicator(application, f"/ws/threads/{thread.id}/")
    communicator.scope["headers"] = [(b"authorization", f"Bearer {token}".encode())]

    connected, close_code = await communicator.connect()
    assert not connected
    assert close_code == 4403
