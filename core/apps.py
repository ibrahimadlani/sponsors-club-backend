"""Application configuration for the core project helpers."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Register management utilities that live in the core package.

    Attributes:
        default_auto_field: The primary key type applied to new models.
        name: Django application label used for configuration discovery.
        verbose_name: Human readable label displayed in admin interfaces.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core Utilities"
