"""API view tests covering the notification list and read endpoints."""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse
from rest_framework import status

pytest.importorskip("channels")

from core.feature_matrix import FEATURE_MATRIX
from notifications.models import Notification


@pytest.mark.django_db
def test_notification_list_view_orders_and_filters(
    api_client,
    organisations_setup,
    user_model,
):
    """The list endpoint should return the caller's notifications only."""

    owner = organisations_setup["owner"]
    other_user = user_model.objects.create_user(
        email="other@test.com",
        password="pass1234",
        first_name="Other",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )

    older = Notification.objects.create(
        user=owner,
        type=Notification.Type.CONTRACT_STATUS,
        payload={"index": 0},
        is_read=True,
    )
    newest = Notification.objects.create(
        user=owner,
        type=Notification.Type.NEW_MESSAGE,
        payload={"index": 1},
        is_read=False,
    )
    Notification.objects.create(
        user=other_user,
        type=Notification.Type.PAYMENT,
        payload={"index": 2},
    )

    api_client.force_authenticate(owner)
    url = reverse("notifications-list")

    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()

    assert payload["count"] == 2
    assert [item["id"] for item in payload["results"]] == [
        str(newest.id),
        str(older.id),
    ]

    read_response = api_client.get(url, {"is_read": "true"})
    assert read_response.status_code == status.HTTP_200_OK
    read_payload = read_response.json()
    assert read_payload["count"] == 1
    assert read_payload["results"][0]["id"] == str(older.id)

    unread_response = api_client.get(url, {"is_read": "false"})
    assert unread_response.status_code == status.HTTP_200_OK
    unread_payload = unread_response.json()
    assert unread_payload["count"] == 1
    assert unread_payload["results"][0]["id"] == str(newest.id)


@pytest.mark.django_db
def test_notification_read_view_updates_state(api_client, organisations_setup):
    """PATCHing the read endpoint should toggle the notification state."""

    owner = organisations_setup["owner"]
    notification = Notification.objects.create(
        user=owner,
        type=Notification.Type.NEW_MESSAGE,
        payload={"message": "hello"},
        is_read=False,
    )

    api_client.force_authenticate(owner)
    url = reverse("notifications-read", args=[notification.id])

    response = api_client.patch(url, {"is_read": True}, format="json")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["id"] == str(notification.id)
    assert body["is_read"] is True

    notification.refresh_from_db()
    assert notification.is_read is True


@pytest.mark.django_db
def test_notification_read_view_rejects_missing_notification(
    api_client,
    organisations_setup,
    user_model,
):
    """A 404 should be returned when the notification does not exist."""

    owner = organisations_setup["owner"]
    other_user = user_model.objects.create_user(
        email="missing@test.com",
        password="pass1234",
        first_name="Missing",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    other_notification = Notification.objects.create(
        user=other_user,
        type=Notification.Type.STAT_UPDATE,
        payload={"index": 3},
    )

    api_client.force_authenticate(owner)
    url = reverse("notifications-read", args=[other_notification.id])

    response = api_client.patch(url, {"is_read": True}, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Notification not found."}

    # Using a completely random identifier should behave the same way.
    missing_url = reverse("notifications-read", args=[uuid.uuid4()])
    missing_response = api_client.patch(missing_url, {"is_read": False}, format="json")
    assert missing_response.status_code == status.HTTP_404_NOT_FOUND
    assert missing_response.json() == {"detail": "Notification not found."}


@pytest.mark.django_db
def test_notification_read_view_enforces_feature_requirement(api_client, agent_user):
    """Agents without the notification feature should receive a 403 denial."""

    notification = Notification.objects.create(
        user=agent_user,
        type=Notification.Type.NEW_MESSAGE,
        payload={},
    )

    api_client.force_authenticate(agent_user)
    url = reverse("notifications-read", args=[notification.id])

    response = api_client.patch(url, {"is_read": True}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN

    denial = response.json()
    assert denial["required_feature"] == "notification_center"
    requirement = FEATURE_MATRIX["agent"]["notification_center"]
    expected_detail = (
        requirement.denied_message or "Upgrade required to access notifications."
    )
    assert denial["detail"] == expected_detail
    allowed_values = denial["allowed_values"]
    if allowed_values is not None:
        assert isinstance(allowed_values, (list, tuple))
    assert "recommended_plans" in denial
    assert "upgrade_url" in denial
