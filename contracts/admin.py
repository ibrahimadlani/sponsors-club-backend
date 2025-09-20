"""Admin registrations for contract management models."""

from django.contrib import admin

from .models import ClauseTemplate, Contract, ContractClause, ContractFile, ContractRevision


@admin.register(ClauseTemplate)
class ClauseTemplateAdmin(admin.ModelAdmin):
    """Display clause templates with filtering on category and mandatory flag."""

    list_display = ("title", "category", "version", "is_mandatory")
    list_filter = ("category", "is_mandatory")
    search_fields = ("title", "content")


class ContractClauseInline(admin.TabularInline):
    """Inline editor for clauses attached to a contract."""

    model = ContractClause
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    """Expose contract metadata and allow inline clause editing."""

    list_display = ("title", "organisation", "agent", "status", "effective_date")
    list_filter = ("status", "organisation")
    search_fields = ("title", "organisation__name", "agent__display_name")
    inlines = [ContractClauseInline]


@admin.register(ContractRevision)
class ContractRevisionAdmin(admin.ModelAdmin):
    """Allow staff to inspect revision history between parties."""

    list_display = ("contract", "proposed_by", "accepted", "created_at")
    list_filter = ("accepted",)
    search_fields = ("contract__title", "proposed_by__email")
    filter_horizontal = ("clauses_changed",)


@admin.register(ContractFile)
class ContractFileAdmin(admin.ModelAdmin):
    """Expose generated PDF exports for download."""

    list_display = ("contract", "created_at")
    search_fields = ("contract__title",)
