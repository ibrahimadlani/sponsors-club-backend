"""Application configuration for the athletes app."""

# The configuration class ensures Django discovers signals and default settings
# for the athletes application.

from django.apps import AppConfig


class AthletesConfig(AppConfig):
    """Register the athletes app with Django.

    Attributes:
        default_auto_field (str): Field type used for automatically added
            primary keys.
        name (str): Fully-qualified application label used by Django.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "athletes"
