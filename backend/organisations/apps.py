"""Application configuration for the organisations app."""

from django.apps import AppConfig


class OrganisationsConfig(AppConfig):
    """Register the organisations application with Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "organisations"
