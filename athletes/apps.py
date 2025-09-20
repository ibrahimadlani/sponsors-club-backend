"""Application configuration for the athletes app."""

from django.apps import AppConfig


class AthletesConfig(AppConfig):
    """Register the athletes app with Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "athletes"
