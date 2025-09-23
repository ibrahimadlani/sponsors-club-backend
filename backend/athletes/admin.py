"""Admin registrations for athletes and sports."""

from django.contrib import admin

from .models import Athlete, Sport


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    """Expose sport metadata with searchable fields."""

    list_display = ("name", "discipline")
    search_fields = ("name", "discipline")


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    """Provide rich admin filters for athlete management."""

    list_display = ("full_name", "sport", "agent", "nationality", "is_self_represented")
    list_filter = ("sport", "nationality", "is_self_represented")
    search_fields = (
        "full_name",
        "sport__name",
        "agent__display_name",
        "agent__user__email",
    )
