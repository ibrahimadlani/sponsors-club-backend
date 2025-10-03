"""Application configuration for the organisations app."""

from django.apps import AppConfig


class OrganisationsConfig(AppConfig):
    """Register the organisations application with Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "organisations"

    def ready(self):  # pragma: no cover - import-time side effects
        # Import signal handlers so any future hooks register during app load.
        from . import signals  # noqa: F401
