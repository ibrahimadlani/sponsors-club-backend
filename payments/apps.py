"""Application configuration for the payments app."""

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """App configuration used by Django during startup.

    Attributes:
        default_auto_field (str): Auto field type applied to models without an
            explicit primary key declaration.
        name (str): Python path of the payments application package.
    """

    # Django uses this setting when generating migrations for UUID primary keys.
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"
