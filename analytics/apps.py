"""Application configuration for the analytics app."""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Register analytics within Django."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
