"""Utilities for delivering transactional emails via Amazon SES."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Sequence

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when Amazon SES rejects or fails to deliver a message."""


@dataclass
class EmailMessage:
    """Structured representation of an outbound email."""

    subject: str
    to_addresses: Sequence[str]
    text_body: str | None = None
    html_body: str | None = None
    source: str | None = None
    reply_to: Sequence[str] | None = None
    configuration_set: str | None = None
    tags: Sequence[tuple[str, str]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.text_body and not self.html_body:
            raise ValueError("EmailMessage requires at least one body variant")
        if not self.to_addresses:
            raise ValueError("EmailMessage requires at least one recipient")


def _ses_client():
    """Return a cached boto3 SES client configured from Django settings."""

    return _build_ses_client()


@lru_cache(maxsize=1)
def _build_ses_client():
    params: dict[str, object] = {"region_name": settings.AWS_SES_REGION_NAME}
    if settings.AWS_SES_ACCESS_KEY_ID and settings.AWS_SES_SECRET_ACCESS_KEY:
        params.update(
            {
                "aws_access_key_id": settings.AWS_SES_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SES_SECRET_ACCESS_KEY,
            }
        )
    return boto3.client("ses", **params)


def send_email(message: EmailMessage) -> None:
    """Send the provided email message via Amazon SES."""

    client = _ses_client()
    body: dict[str, dict[str, str]] = {}
    if message.text_body:
        body["Text"] = {"Data": message.text_body, "Charset": "UTF-8"}
    if message.html_body:
        body["Html"] = {"Data": message.html_body, "Charset": "UTF-8"}

    destination = {"ToAddresses": list(message.to_addresses)}
    tag_list = [
        {"Name": tag_name, "Value": tag_value} for tag_name, tag_value in message.tags
    ]

    request: dict[str, object] = {
        "Destination": destination,
        "Message": {
            "Body": body,
            "Subject": {"Data": message.subject, "Charset": "UTF-8"},
        },
        "Source": message.source or settings.AWS_SES_SOURCE_EMAIL,
    }

    if message.reply_to:
        request["ReplyToAddresses"] = list(message.reply_to)
    configuration_set = message.configuration_set or settings.AWS_SES_CONFIGURATION_SET
    if configuration_set:
        request["ConfigurationSetName"] = configuration_set
    if tag_list:
        request["Tags"] = tag_list

    try:
        client.send_email(**request)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - defensive
        logger.exception("Failed to deliver email via Amazon SES")
        raise EmailDeliveryError("Amazon SES rejected the message") from exc


def send_bulk(messages: Iterable[EmailMessage]) -> None:
    """Send a series of messages sequentially while sharing the SES client."""

    for message in messages:
        try:
            send_email(message)
        except EmailDeliveryError:
            # send_email already logged the failure; continue with other messages.
            continue


__all__ = ["EmailDeliveryError", "EmailMessage", "send_email", "send_bulk"]
