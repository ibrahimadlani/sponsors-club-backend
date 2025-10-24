"""Django command to wait for the database to be available."""

import time

from psycopg2 import OperationalError as Psycopg2OpError

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Django command to wait for database."""

    DEFAULT_SLEEP_SECONDS = 1
    MAX_SLEEP_SECONDS = 5

    def handle(self, *args, **options):
        """Entrypoint for command."""
        self.stdout.write("Waiting for database...")

        sleep_seconds = self.DEFAULT_SLEEP_SECONDS
        while True:
            connection = connections["default"]
            try:
                connection.ensure_connection()
            except (Psycopg2OpError, OperationalError):
                self.stdout.write(
                    f"Database unavailable, waiting {sleep_seconds} second(s)..."
                )
                time.sleep(sleep_seconds)
                sleep_seconds = min(sleep_seconds * 2, self.MAX_SLEEP_SECONDS)
            else:
                connection.close()
                break

        self.stdout.write(self.style.SUCCESS("Database available!"))
