"""Messaging thread creation integration tests."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from organisations.models import Collaborator


@pytest.fixture(name='thread_payload_data')
def fixture_thread_payload(agent_user, organisations_setup):
    """Return the canonical payload for creating a thread."""

    collaborator = organisations_setup['collaborator']
    return {
        'collaborator_id': str(collaborator.id),
        'agent_id': str(agent_user.agent_profile.id),
    }


@pytest.mark.django_db
def test_agent_without_subscription_cannot_create_thread(agent_user, thread_payload_data):
    """Agents without the messaging feature should be denied."""

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('messaging-thread-list')
    response = client.post(url, thread_payload_data, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload['required_feature'] == 'messaging_tier'
    assert 'Pro+' in payload['detail']


@pytest.mark.django_db
def test_agent_with_subscription_can_create_thread(
    agent_user,
    agent_subscription,
    thread_payload_data,
):
    """Agents with an appropriate subscription should create threads successfully."""

    del agent_subscription

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('messaging-thread-list')
    response = client.post(url, thread_payload_data, format='json')
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_collaborator_can_create_thread(owner_user, agent_user):
    """Collaborators may create threads when selecting an agent."""

    payload = {
        'agent_id': str(agent_user.agent_profile.id),
    }
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse('messaging-thread-list')
    response = client.post(url, payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert Collaborator.objects.filter(user=owner_user).exists()
