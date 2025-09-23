"""App configuration for the messaging Django application."""

from django.apps import AppConfig


class MessagingConfig(AppConfig):
    """Identify the messaging app and wire its configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "messaging"
