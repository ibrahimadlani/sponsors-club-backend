"""Application configuration for the users app."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Register the users application with Django."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
