"""Admin registrations for organisation-related models."""

from django.contrib import admin

from .models import Collaborator, Organisation


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    """Admin configuration for managing organisations."""

    list_display = ("name", "sector", "size", "country")
    list_filter = ("size", "country")
    search_fields = ("name", "sector", "country")


@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    """Admin configuration for organisation collaborators."""

    list_display = ("user", "organisation", "role", "job_title")
    list_filter = ("role", "organisation")
    search_fields = ("user__email", "organisation__name", "job_title")
