"""Admin configuration for messaging models.

The Django admin panels are designed for support staff who occasionally need to
inspect conversations, so the configuration focuses on discoverability.
"""

from django.contrib import admin

from .constants import THREAD_PARTICIPANT_COLUMNS
from .models import Message, Thread


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    """Display messaging threads with participant filters.

    Keeping participant information in ``list_display`` provides an at-a-glance
    overview of who is involved in a conversation, which is helpful during
    customer support escalations.
    """

    list_display = THREAD_PARTICIPANT_COLUMNS
    list_filter = ("athlete",)
    search_fields = (
        "collaborator__user__email",
        "agent__user__email",
        "athlete__full_name",
    )
    ordering = ("-last_message_at", "-created_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Expose basic metadata for individual messages.

    Including search across message content allows support teams to retrieve
    problematic messages without navigating through every thread manually.
    """

    list_display = ("thread", "sender", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = (
        "thread__collaborator__user__email",
        "thread__agent__user__email",
        "content",
    )
    ordering = ("-created_at",)
