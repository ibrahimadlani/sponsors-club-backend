"""Admin registrations for organisation-related models."""

from django.contrib import admin

from .models import Collaborator, Organisation, OrganisationInvite


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    """Admin configuration for managing organisations."""

    list_display = ("name", "type", "industry", "address_country", "slug")
    list_filter = ("type", "address_country")
    search_fields = ("name", "industry", "address_country", "slug")


@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    """Admin configuration for organisation collaborators."""

    list_display = ("user", "organisation", "role", "job_title")
    list_filter = ("role", "organisation")
    search_fields = ("user__email", "organisation__name", "job_title")


@admin.register(OrganisationInvite)
class OrganisationInviteAdmin(admin.ModelAdmin):
    """Admin configuration for organisation invitation codes."""

    list_display = ("code", "organisation", "created_by", "expires_at", "is_used")
    list_filter = ("is_used", "organisation")
    search_fields = ("code", "organisation__name", "created_by__user__email")
