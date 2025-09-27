import pytest

from core.emails import EmailDeliveryError
from users import emails as user_emails


@pytest.mark.django_db
def test_send_email_verification_uses_template_and_context(monkeypatch, settings, user_model):
    settings.EMAIL_VERIFICATION_URL_TEMPLATE = "https://example.com/verify/{uid}/{token}"

    user = user_model.objects.create_user(email="template@example.com", password="pass1234")

    issued_tokens = {}
    monkeypatch.setattr(
        user_emails.EmailVerificationToken,
        "issue_for_user",
        lambda instance: issued_tokens.setdefault("token", "issued-token"),
    )

    rendered_templates = {}

    def fake_render(template_name, context):
        rendered_templates.setdefault(template_name, []).append(context)
        return f"rendered:{template_name}"

    monkeypatch.setattr(user_emails, "render_to_string", fake_render)

    captured_messages = []
    monkeypatch.setattr(user_emails, "send_email", lambda message: captured_messages.append(message))

    user_emails.send_email_verification(user)

    assert captured_messages, "Expected the helper to send an email"
    message = captured_messages[0]
    assert message.to_addresses == [user.email]
    assert message.text_body.startswith("rendered:")
    assert issued_tokens["token"] == "issued-token"

    rendered_contexts = rendered_templates["emails/users/verification.txt"][0]
    assert rendered_contexts["verification_url"] == "https://example.com/verify/{uid}/{token}".format(
        uid=str(user.id),
        token="issued-token",
    )


@pytest.mark.django_db
def test_send_email_verification_logs_delivery_error(monkeypatch, settings, user_model, caplog):
    settings.EMAIL_VERIFICATION_URL_TEMPLATE = None
    user = user_model.objects.create_user(email="failure@example.com", password="pass1234")

    monkeypatch.setattr(user_emails.EmailVerificationToken, "issue_for_user", lambda _: "token")
    monkeypatch.setattr(user_emails, "render_to_string", lambda *_args, **_kwargs: "body")

    def raise_delivery_error(_message):
        raise EmailDeliveryError("fail")

    monkeypatch.setattr(user_emails, "send_email", raise_delivery_error)

    with caplog.at_level("ERROR"):
        user_emails.send_email_verification(user)

    assert any("Failed to send verification email" in record.getMessage() for record in caplog.records)
