"""Application configuration for payments."""

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Configure the payments Django application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"
