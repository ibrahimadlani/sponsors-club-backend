"""Admin registrations for contracts domain models."""

from django.contrib import admin

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractComment,
    ContractFile,
    ContractLegalReview,
    ContractRevision,
    ContractSigning,
    ContractVersion,
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


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = ("contract", "number", "created_by", "created_at")
    search_fields = ("contract__title", "created_by__email")
    ordering = ("-created_at",)


@admin.register(ContractComment)
class ContractCommentAdmin(admin.ModelAdmin):
    list_display = ("contract", "version", "author", "created_at")
    search_fields = (
        "contract__title",
        "author__email",
        "body",
    )
    list_filter = ("version",)


@admin.register(ContractLegalReview)
class ContractLegalReviewAdmin(admin.ModelAdmin):
    list_display = ("contract", "requested_by", "verified_by", "created_at")
    search_fields = (
        "contract__title",
        "requested_by__email",
        "verified_by__email",
    )


@admin.register(ContractSigning)
class ContractSigningAdmin(admin.ModelAdmin):
    list_display = ("contract", "envelope_id", "status", "created_at")
    search_fields = ("contract__title", "envelope_id")
    list_filter = ("status",)
