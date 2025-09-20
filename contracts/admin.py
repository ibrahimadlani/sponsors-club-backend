"""Admin registrations for the contracts application."""

from django.contrib import admin

from .models import ClauseTemplate, Contract, ContractClause, ContractFile, ContractRevision


@admin.register(ClauseTemplate)
class ClauseTemplateAdmin(admin.ModelAdmin):
    """Display clause templates with filtering by category and version."""

    list_display = ("title", "category", "version", "is_mandatory", "is_active")
    list_filter = ("category", "is_mandatory", "is_active")
    search_fields = ("title", "content")


class ContractClauseInline(admin.TabularInline):
    """Inline editor for contract clauses."""

    model = ContractClause
    extra = 0
    fields = ("title", "is_mandatory", "is_modified", "position")
    readonly_fields = ("is_mandatory", "is_modified")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    """Expose contracts with their clauses for quick review."""

    list_display = (
        "title",
        "organisation",
        "agent",
        "status",
        "effective_date",
        "expiration_date",
    )
    list_filter = ("status", "organisation")
    search_fields = ("title", "organisation__name", "agent__display_name")
    inlines = [ContractClauseInline]


@admin.register(ContractClause)
class ContractClauseAdmin(admin.ModelAdmin):
    """Allow direct inspection of individual contract clauses."""

    list_display = ("contract", "title", "is_mandatory", "is_modified", "position")
    list_filter = ("is_mandatory", "is_modified")
    search_fields = ("title", "content", "contract__title")


@admin.register(ContractRevision)
class ContractRevisionAdmin(admin.ModelAdmin):
    """Manage proposed contract revisions from the admin panel."""

    list_display = ("contract", "proposed_by", "accepted", "created_at")
    list_filter = ("accepted",)
    search_fields = ("contract__title", "proposed_by__email")
    filter_horizontal = ("clauses_changed",)


@admin.register(ContractFile)
class ContractFileAdmin(admin.ModelAdmin):
    """Expose stored contract exports."""

    list_display = ("contract", "created_at")
    search_fields = ("contract__title", "contract__organisation__name")
