"""Admin registrations for contracts domain models."""

from django.contrib import admin

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractFile,
    ContractRevision,
)


@admin.register(ClauseTemplate)
class ClauseTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "version", "is_mandatory")
    list_filter = ("category", "is_mandatory")
    search_fields = ("title", "category")


class ContractClauseInline(admin.TabularInline):
    model = ContractClause
    extra = 0
    fields = ("title", "is_mandatory", "is_modified")
    readonly_fields = ("is_mandatory", "is_modified")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("title", "organisation", "agent", "status", "effective_date")
    list_filter = ("status", "organisation")
    search_fields = ("title", "organisation__name", "agent__display_name")
    inlines = [ContractClauseInline]


@admin.register(ContractRevision)
class ContractRevisionAdmin(admin.ModelAdmin):
    list_display = ("contract", "proposed_by", "accepted", "created_at")
    list_filter = ("accepted",)
    search_fields = ("contract__title", "proposed_by__email")
    filter_horizontal = ("clauses_changed",)


@admin.register(ContractFile)
class ContractFileAdmin(admin.ModelAdmin):
    list_display = ("contract", "created_at")
    search_fields = ("contract__title",)
