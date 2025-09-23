import pytest
from unittest.mock import MagicMock

from notifications.models import Notification


@pytest.mark.django_db
def test_notification_email_sent_for_verified_user(monkeypatch, user_model):
    user = user_model.objects.create_user(
        email="notify@example.com",
        password="pass1234",
    )
    user.email_verified = True
    user.save(update_fields=["email_verified", "updated_at"])

    captured = {}

    def fake_send_email(message):
        captured["message"] = message

    monkeypatch.setattr("notifications.emails.send_email", fake_send_email)

    Notification.objects.create(
        user=user,
        type=Notification.Type.NEW_MESSAGE,
        payload={"thread_id": "abc123"},
    )

    assert "message" in captured
    assert captured["message"].to_addresses == ["notify@example.com"]


@pytest.mark.django_db
def test_notification_email_skipped_when_unverified(monkeypatch, user_model):
    user = user_model.objects.create_user(
        email="skip@example.com",
        password="pass1234",
    )

    mock_send = MagicMock()
    monkeypatch.setattr("notifications.emails.send_email", mock_send)

    Notification.objects.create(
        user=user,
        type=Notification.Type.NEW_MESSAGE,
        payload={"thread_id": "abc123"},
    )

    mock_send.assert_not_called()
