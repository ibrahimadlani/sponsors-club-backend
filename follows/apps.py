"""Django application configuration for the follows domain.

The configuration file is a convenient place to explain when runtime hooks
such as signal registration happen, providing clearer onboarding for new
contributors.
"""

from django.apps import AppConfig


class FollowsConfig(AppConfig):
    """Configure runtime behaviour for the follows Django application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "follows"

    def ready(self):
        """Register signal handlers used to maintain cached follower counts."""

        # Importing within ``ready`` ensures signal modules are loaded exactly
        # once when Django starts, avoiding circular imports during tests.
        from . import signals  # noqa: F401  pylint: disable=unused-import

