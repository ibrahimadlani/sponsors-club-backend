"""Application configuration for the contracts app.

Keeping the configuration explicit makes the app easy to plug into test
sandboxes without guessing settings such as the default auto field.
"""

from django.apps import AppConfig


class ContractsConfig(AppConfig):
    """Register and describe the contracts Django application.

    Attributes:
        default_auto_field: Ensures UUID and foreign keys default to big ints.
        name: App label used by Django for routing and migrations.
    """

    default_auto_field = "django.db.models.BigAutoField"
    # Using the dotted path keeps Django's app registry consistent across
    # production and test environments.
    name = "contracts"
