"""App configuration for the messaging Django application.

Keeping the config in its own module documents the app label and leaves room
for future startup hooks such as signal registration without bloating
``__init__``.
"""

from django.apps import AppConfig


class MessagingConfig(AppConfig):
    """Identify the messaging app and wire its configuration.

    Attributes:
        default_auto_field (str): Default field type for primary keys.
        name (str): Application label used by Django.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "messaging"
