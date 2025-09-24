"""Administrative configuration for managing follow relationships.

The admin surface is primarily used by support staff to audit who follows
which athletes and to diagnose notification issues. Adding a richer
docstring makes that workflow explicit for future maintainers.
"""

from django.contrib import admin

from .models import Follow


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Configure how :class:`follows.models.Follow` entries appear in admin.

    Attributes:
        list_display: Columns that provide at-a-glance context for support
            staff—namely who is following whom and which notifications are
            enabled.
        list_filter: Boolean toggles that allow narrowing to specific
            notification preferences during troubleshooting.
        search_fields: Fields used to look up records by email or athlete
            name when responding to help-desk tickets.
        ordering: Default ordering surfaces the most recent follows first so
            new activity is immediately visible.
    """

    list_display = (
        "collaborator",
        "athlete",
        "created_at",
        "notify_news",
        "notify_stats",
        "notify_contracts",
    )
    # Filtering by each notification toggle helps support staff understand why
    # a collaborator may or may not receive a specific alert category.
    list_filter = ("notify_news", "notify_stats", "notify_contracts")
    # Email and athlete name are the two pieces of information most commonly
    # provided in support tickets, hence they are indexed for quick lookup.
    search_fields = ("collaborator__user__email", "athlete__full_name")
    ordering = ("-created_at",)
