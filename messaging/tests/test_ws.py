"""WebSocket integration tests for the messaging thread consumer."""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from messaging.consumers import JWTAuthMiddlewareStack
from messaging.models import Message, Thread
from messaging.routing import websocket_urlpatterns
from organisations.models import Collaborator, Organisation


@pytest.mark.django_db(transaction=True)
def test_thread_consumer_broadcasts_message(agent_user, user_model):
    collaborator_user = user_model.objects.create_user(
        email="collab@test.com",
        password="pass1234",
        first_name="Col",
        last_name="Lab",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(
        owner=collaborator_user,
        name="Org",
        sector="Tech",
        size=Organisation.Size.SMALL,
        budget_min=1000,
        budget_max=2000,
        country="FR",
    )
    collaborator = Collaborator.objects.create(
        user=collaborator_user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    thread = Thread.objects.create(collaborator=collaborator, agent=agent_user.agent_profile)

    application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    token = RefreshToken.for_user(collaborator_user).access_token
    headers = [(b"authorization", f"Bearer {token}".encode())]

    async def scenario():
        communicator = WebsocketCommunicator(
            application,
            f"/ws/threads/{thread.id}/",
            headers=headers,
        )
        connected, _ = await communicator.connect()
        assert connected is True

        await communicator.send_json_to({"content": "Realtime hello"})
        response = await communicator.receive_json_from()
        await communicator.disconnect()
        return response

    with override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ):
        payload = async_to_sync(scenario)()

    assert payload["content"] == "Realtime hello"
    assert payload["thread"] == str(thread.id)
    assert payload["sender"] == str(collaborator_user.id)
    assert Message.objects.filter(thread=thread).count() == 1


@pytest.mark.django_db(transaction=True)
def test_thread_consumer_rejects_non_participant(agent_user, user_model):
    collaborator_user = user_model.objects.create_user(
        email="collab2@test.com",
        password="pass1234",
        first_name="Col",
        last_name="Lab",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(
        owner=collaborator_user,
        name="Org 2",
        sector="Tech",
        size=Organisation.Size.SMALL,
        budget_min=1000,
        budget_max=2000,
        country="FR",
    )
    collaborator = Collaborator.objects.create(
        user=collaborator_user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    thread = Thread.objects.create(collaborator=collaborator, agent=agent_user.agent_profile)

    outsider = user_model.objects.create_user(
        email="outsider@test.com",
        password="pass1234",
        first_name="Out",
        last_name="Sider",
        account_type=user_model.AccountType.COLLABORATOR,
    )

    application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    token = RefreshToken.for_user(outsider).access_token
    headers = [(b"authorization", f"Bearer {token}".encode())]

    async def scenario():
        communicator = WebsocketCommunicator(
            application,
            f"/ws/threads/{thread.id}/",
            headers=headers,
        )
        connected, _ = await communicator.connect()
        await communicator.disconnect()
        return connected

    with override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ):
        connected = async_to_sync(scenario)()

    assert connected is False
    assert Message.objects.count() == 0
