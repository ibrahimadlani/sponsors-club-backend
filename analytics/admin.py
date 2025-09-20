"""Admin registrations for analytics models."""

from django.contrib import admin

from .models import AthleteSocialAccount, DailyStats, SocialPlatform


@admin.register(SocialPlatform)
class SocialPlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "created_at")
    search_fields = ("name",)


@admin.register(AthleteSocialAccount)
class AthleteSocialAccountAdmin(admin.ModelAdmin):
    list_display = ("athlete", "platform", "username", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("athlete__full_name", "username", "external_id")


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ("account", "date", "followers", "engagement_rate")
    list_filter = ("account__platform", "date")
    search_fields = ("account__athlete__full_name", "account__username")
    ordering = ("-date",)
