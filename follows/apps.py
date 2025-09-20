"""App configuration for the follows application."""

from django.apps import AppConfig


class FollowsConfig(AppConfig):
    """Configure the follows Django application."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'follows'

    def ready(self):
        pass
