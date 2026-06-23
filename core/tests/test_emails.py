import types
from typing import Any

import pytest

from core import emails


@pytest.fixture(autouse=True)
def clear_ses_cache():
    """Ensure the cached SES client is reset between tests."""

    emails._build_ses_client.cache_clear()
    yield
    emails._build_ses_client.cache_clear()


def test_email_message_requires_body():
    with pytest.raises(ValueError):
        emails.EmailMessage(subject="Welcome", to_addresses=["user@example.com"])


def test_email_message_requires_recipient():
    with pytest.raises(ValueError):
        emails.EmailMessage(
            subject="Update",
            to_addresses=[],
            text_body="Plain text",
        )


def test_build_ses_client_uses_credentials(settings, monkeypatch):
    settings.AWS_SES_REGION_NAME = "eu-west-1"
    settings.AWS_SES_ACCESS_KEY_ID = "access"
    settings.AWS_SES_SECRET_ACCESS_KEY = "secret"

    captured: dict[str, Any] = {}

    def fake_client(service_name: str, **kwargs: Any) -> str:
        captured["service"] = service_name
        captured["params"] = kwargs
        return "client"

    monkeypatch.setattr(emails, "boto3", types.SimpleNamespace(client=fake_client))

    client = emails._build_ses_client()

    assert client == "client"
    assert captured["service"] == "ses"
    assert captured["params"] == {
        "region_name": "eu-west-1",
        "aws_access_key_id": "access",
        "aws_secret_access_key": "secret",
    }


def test_send_email_builds_request(settings, monkeypatch):
    settings.AWS_SES_REGION_NAME = "eu-west-1"
    settings.AWS_SES_SOURCE_EMAIL = "default@example.com"
    settings.AWS_SES_CONFIGURATION_SET = "global-config"

    sent: dict[str, Any] = {}

    class DummyClient:
        def send_email(self, **kwargs: Any) -> None:
            sent.update(kwargs)

    monkeypatch.setattr(emails, "_ses_client", lambda: DummyClient())

    message = emails.EmailMessage(
        subject="Welcome",
        to_addresses=["user@example.com"],
        text_body="Hello",
        html_body="<p>Hello</p>",
        source="support@example.com",
        reply_to=["reply@example.com"],
        configuration_set="custom-config",
        tags=(("campaign", "spring"),),
    )

    emails.send_email(message)

    assert sent["Source"] == "support@example.com"
    assert sent["ConfigurationSetName"] == "custom-config"
    assert sent["Tags"] == [{"Name": "campaign", "Value": "spring"}]
    assert sent["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert sent["Message"]["Subject"] == {"Data": "Welcome", "Charset": "UTF-8"}
    assert sent["Message"]["Body"] == {
        "Text": {"Data": "Hello", "Charset": "UTF-8"},
        "Html": {"Data": "<p>Hello</p>", "Charset": "UTF-8"},
    }


def test_send_email_uses_defaults(settings, monkeypatch):
    settings.AWS_SES_REGION_NAME = "eu-west-1"
    settings.AWS_SES_SOURCE_EMAIL = "no-reply@example.com"
    settings.AWS_SES_CONFIGURATION_SET = ""

    sent: dict[str, Any] = {}

    class DummyClient:
        def send_email(self, **kwargs: Any) -> None:
            sent.update(kwargs)

    monkeypatch.setattr(emails, "_ses_client", lambda: DummyClient())

    message = emails.EmailMessage(
        subject="Reset",
        to_addresses=["user@example.com"],
        text_body="Reset instructions",
    )

    emails.send_email(message)

    assert sent["Source"] == "no-reply@example.com"
    assert "ConfigurationSetName" not in sent
    assert "Tags" not in sent
    assert sent["Message"]["Body"] == {
        "Text": {"Data": "Reset instructions", "Charset": "UTF-8"}
    }


def test_send_bulk_continues_after_failures(monkeypatch):
    messages = [
        emails.EmailMessage(
            subject="One",
            to_addresses=["a@example.com"],
            text_body="1",
        ),
        emails.EmailMessage(
            subject="Two",
            to_addresses=["b@example.com"],
            text_body="2",
        ),
    ]

    calls: list[str] = []

    def fake_send_email(message: emails.EmailMessage) -> None:
        calls.append(message.subject)
        if message.subject == "One":
            raise emails.EmailDeliveryError("boom")

    monkeypatch.setattr(emails, "send_email", fake_send_email)

    emails.send_bulk(messages)

    assert calls == ["One", "Two"]
