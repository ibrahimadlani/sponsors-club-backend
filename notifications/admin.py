"""Admin configuration for notification models.

The admin registration mirrors what agents see in the notification center so
support staff can confirm the payload users received when debugging.
"""

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Display notification metadata in the Django admin.

    Attributes:
        list_display (tuple[str, ...]): Columns shown on the changelist view so
            staff can review the recipient, type, and read status at a glance.
        list_filter (tuple[str, ...]): Sidebar filters that help teams focus on
            unread items or specific notification categories.
        search_fields (tuple[str, ...]): Fields indexed for quick lookups by
            email address or payload snippets.
        ordering (tuple[str, ...]): Default ordering, matching the API sorting
            to keep admin expectations aligned with the product.
    """

    list_display = ("user", "type", "is_read", "created_at")
    list_filter = ("type", "is_read")
    search_fields = ("user__email", "payload")
    ordering = ("-created_at",)

    # Admin automatically leverages the list and filter settings above, so no
    # additional customisations are required for common support workflows.
