"""Management command to clean up expired invitation codes."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from organisations.models import OrganisationInvite


class Command(BaseCommand):
    """Clean up expired and old invitation codes."""

    help = "Delete expired invitation codes older than a specified number of days"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete invites expired more than X days ago (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--include-used",
            action="store_true",
            help="Also delete used invitations (default: only unused)",
        )

    def handle(self, *args, **options):
        """Execute the cleanup command."""
        days = options["days"]
        dry_run = options["dry_run"]
        include_used = options["include_used"]

        cutoff_date = timezone.now() - timedelta(days=days)

        # Build the queryset
        queryset = OrganisationInvite.objects.filter(expires_at__lt=cutoff_date)

        if not include_used:
            queryset = queryset.filter(is_used=False)

        count = queryset.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY RUN] Would delete {count} invitation(s)")
            )
            if count > 0:
                # Show sample of what would be deleted
                samples = queryset[:5]
                self.stdout.write("\nSample invitations that would be deleted:")
                for invite in samples:
                    status_str = "used" if invite.is_used else "unused"
                    self.stdout.write(
                        f"  - Code: {invite.code}, "
                        f"Expired: {invite.expires_at.strftime('%Y-%m-%d')}, "
                        f"Status: {status_str}, "
                        f"Org: {invite.organisation.name}"
                    )
                if count > 5:
                    self.stdout.write(f"  ... and {count - 5} more")
            return

        # Actually delete
        deleted_count, _ = queryset.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {deleted_count} expired invitation(s)"
            )
        )
