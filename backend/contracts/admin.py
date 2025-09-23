"""Admin registrations for contract templates, versions, and status history."""

from django.contrib import admin

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractStatusHistory,
    ContractVersion,
)


@admin.register(ClauseTemplate)
class ClauseTemplateAdmin(admin.ModelAdmin):
    """Display clause templates with version and activation filters."""

    list_display = (
        "identifier",
        "title",
        "type",
        "version",
        "mandatory",
        "is_active",
    )
    list_filter = ("type", "mandatory", "is_active")
    search_fields = ("identifier", "title")


class ContractClauseInline(admin.TabularInline):
    """Inline editor for contract clauses."""

    model = ContractClause
    extra = 0


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    """Expose contracts with key metadata and clause inline editing."""

    list_display = (
        "organisation",
        "athlete",
        "status",
        "start_date",
        "end_date",
        "amount",
        "currency",
    )
    list_filter = ("status", "currency", "organisation")
    search_fields = ("organisation__name", "athlete__full_name")
    inlines = [ContractClauseInline]


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    """Allow inspection of stored contract versions."""

    list_display = ("contract", "version_number", "created_at")
    list_filter = ("version_number",)
    search_fields = ("contract__organisation__name", "contract__athlete__full_name")


@admin.register(ContractStatusHistory)
class ContractStatusHistoryAdmin(admin.ModelAdmin):
    """List contract status transitions with audit details."""

    list_display = (
        "contract",
        "from_status",
        "to_status",
        "changed_by",
        "changed_at",
    )
    list_filter = ("to_status",)
    search_fields = (
        "contract__organisation__name",
        "contract__athlete__full_name",
        "changed_by__email",
    )
