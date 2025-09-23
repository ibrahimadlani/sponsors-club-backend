import pytest
from django.urls import reverse

from users.models import EmailVerificationToken


@pytest.mark.django_db
def test_register_sends_verification_email(monkeypatch, api_client):
    captured = {}

    def fake_send_email(message):
        captured["message"] = message

    monkeypatch.setattr("users.emails.send_email", fake_send_email)

    payload = {
        "email": "verify@example.com",
        "password": "pass1234",
        "account_type": "COLLABORATOR",
        "first_name": "Verify",
        "last_name": "User",
    }
    response = api_client.post(reverse("users:register"), payload, format="json")

    assert response.status_code == 201
    assert "message" in captured
    message = captured["message"]
    assert message.to_addresses == ["verify@example.com"]
    assert EmailVerificationToken.objects.filter(user__email="verify@example.com").exists()


@pytest.mark.django_db
def test_verify_email_endpoint_success(api_client, user_model):
    user = user_model.objects.create_user(email="pending@example.com", password="pass1234")
    token = EmailVerificationToken.issue_for_user(user)

    response = api_client.post(
        reverse("users:verify_email"),
        {"uid": str(user.id), "token": token},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email_verified is True


@pytest.mark.django_db
def test_verify_email_endpoint_rejects_invalid_token(api_client, user_model):
    user = user_model.objects.create_user(email="invalid@example.com", password="pass1234")
    EmailVerificationToken.issue_for_user(user)

    response = api_client.post(
        reverse("users:verify_email"),
        {"uid": str(user.id), "token": "wrong"},
        format="json",
    )

    assert response.status_code == 400
    assert "invalid" in response.data["non_field_errors"][0].lower()
