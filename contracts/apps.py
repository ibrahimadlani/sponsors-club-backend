"""Application configuration for the contracts app."""

from django.apps import AppConfig


class ContractsConfig(AppConfig):
    """Register the contracts application with Django."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contracts'
