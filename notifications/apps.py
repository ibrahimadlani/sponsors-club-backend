"""Application configuration for notifications."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Configure the notifications Django app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'
