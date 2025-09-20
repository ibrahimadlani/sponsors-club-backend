"""Admin configuration for notification models."""

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Provide list/search configuration for notifications."""

    list_display = ("user", "type", "is_read", "created_at")
    list_filter = ("type", "is_read")
    search_fields = ("user__email", "payload")
    ordering = ("-created_at",)
