"""Admin configuration for messaging models."""

from django.contrib import admin

from .constants import THREAD_PARTICIPANT_COLUMNS
from .models import Message, Thread


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    """Display messaging threads with participant filters."""

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
    """Expose basic metadata for individual messages."""

    list_display = ("thread", "sender", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = (
        "thread__collaborator__user__email",
        "thread__agent__user__email",
        "content",
    )
    ordering = ("-created_at",)
