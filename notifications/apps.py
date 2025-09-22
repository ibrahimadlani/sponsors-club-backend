"""Application configuration for notifications.

Keeping the app configuration explicit helps Django discover the app when it
is bundled as part of the Sponsors Club project or when tested in isolation.
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Configure the notifications Django app.

    Attributes:
        default_auto_field (str): Field type used for automatically generated
            primary keys in migrations.
        name (str): Full dotted path used by Django when loading the app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
