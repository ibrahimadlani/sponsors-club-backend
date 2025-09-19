"""Admin configuration for managing follows."""

from django.contrib import admin

from .models import Follow


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Expose follow records with useful filtering in the admin site."""

    list_display = (
        'collaborator',
        'athlete',
        'created_at',
        'notify_news',
        'notify_stats',
        'notify_contracts',
    )
    list_filter = ('notify_news', 'notify_stats', 'notify_contracts')
    search_fields = ('collaborator__user__email', 'athlete__full_name')
    ordering = ('-created_at',)
