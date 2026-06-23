"""Admin registrations for contract-related entities.

The admin layer is primarily used by internal staff when they need to inspect
or troubleshoot negotiations, so the list displays and search fields focus on
surfacing the parties involved and the current workflow state.
"""

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
    """Expose reusable clause templates in the admin interface.

    Attributes:
        list_display: Columns that help the legal team distinguish templates.
        list_filter: Sidebar filters to quickly narrow down templates.
        search_fields: Fields indexed by the admin search bar.
    """

    # Surfacing the mandatory flag makes it obvious which clauses get pulled
    # into a new contract by default.
    list_display = ("title", "category", "version", "is_mandatory")
    list_filter = ("category", "is_mandatory")
    search_fields = ("title", "category")


class ContractClauseInline(admin.TabularInline):
    """Inline to visualise the clauses tied to a contract in list form.

    Attributes:
        model: Clause model displayed within the contract edit screen.
        extra: Number of blank clauses shown for quick additions.
        fields: Editable columns rendered in the inline table.
        readonly_fields: Fields locked to prevent accidental edits.
    """

    model = ContractClause
    extra = 0
    # Only clause metadata is editable inline; full content changes go through
    # the dedicated views where validation is stricter.
    fields = ("title", "is_mandatory", "is_modified")
    readonly_fields = ("is_mandatory", "is_modified")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    """Curate the key contract details exposed to staff users.

    Attributes:
        list_display: Primary metadata for spotting the right contract.
        list_filter: Filters that align with common support questions.
        search_fields: Lookups to quickly locate a contract record.
        inlines: Related inlines rendered on the contract change form.
    """

    list_display = ("title", "organisation", "agent", "status", "effective_date")
    list_filter = ("status", "organisation")
    # Searching by organisation name or agent contact mirrors support requests
    # received from account managers.
    search_fields = (
        "title",
        "organisation__name",
        "agent__user__email",
        "agent__user__first_name",
        "agent__user__last_name",
    )
    inlines = [ContractClauseInline]


@admin.register(ContractRevision)
class ContractRevisionAdmin(admin.ModelAdmin):
    """Show a history of proposed changes made during negotiations."""

    list_display = ("contract", "proposed_by", "accepted", "created_at")
    list_filter = ("accepted",)
    search_fields = ("contract__title", "proposed_by__email")
    # Many-to-many clauses benefit from a horizontal widget to stay readable.
    filter_horizontal = ("clauses_changed",)


@admin.register(ContractFile)
class ContractFileAdmin(admin.ModelAdmin):
    """List signed file exports attached to a contract."""

    list_display = ("contract", "created_at")
    search_fields = ("contract__title",)


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    """Expose the timeline of contract versions for audit purposes."""

    list_display = ("contract", "number", "created_by", "created_at")
    search_fields = ("contract__title", "created_by__email")
    ordering = ("-created_at",)


@admin.register(ContractComment)
class ContractCommentAdmin(admin.ModelAdmin):
    """Provide quick access to reviewer feedback on contracts."""

    list_display = ("contract", "version", "author", "created_at")
    search_fields = (
        "contract__title",
        "author__email",
        "body",
    )
    list_filter = ("version",)


@admin.register(ContractLegalReview)
class ContractLegalReviewAdmin(admin.ModelAdmin):
    """Summarise the legal review workflow before signing."""

    list_display = ("contract", "requested_by", "verified_by", "created_at")
    search_fields = (
        "contract__title",
        "requested_by__email",
        "verified_by__email",
    )


@admin.register(ContractSigning)
class ContractSigningAdmin(admin.ModelAdmin):
    """Surface DocuSign envelope activity for support follow-up."""

    list_display = ("contract", "envelope_id", "status", "created_at")
    search_fields = ("contract__title", "envelope_id")
    list_filter = ("status",)
