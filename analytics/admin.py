"""Admin registrations for analytics models."""

from django.contrib import admin

from .models import AthleteStat


@admin.register(AthleteStat)
class AthleteStatAdmin(admin.ModelAdmin):
    """Configure how athlete stats appear in the admin panel."""

    list_display = ('athlete', 'metric', 'value', 'date', 'created_at')
    list_filter = ('metric',)
    search_fields = ('athlete__full_name', 'athlete__sport__name')
    ordering = ('-date',)
