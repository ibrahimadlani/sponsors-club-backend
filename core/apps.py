"""Application configuration for the core project helpers."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Register management utilities that live in the core package."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core Utilities'
