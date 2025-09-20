"""Data models powering the contract management domain."""

from __future__ import annotations

import uuid
from copy import deepcopy

from django.conf import settings
from django.db import models

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


CONTRACT_CONTEXT_STRUCTURE: dict[str, tuple[str, ...]] = {
    "identification": (
        "organisation_name",
        "organisation_legal_name",
        "organisation_type",
        "organisation_registration_number",
        "organisation_tax_id",
        "organisation_address",
        "organisation_country",
        "organisation_representative",
        "organisation_representative_title",
        "athlete_name",
        "athlete_birthdate",
        "athlete_birthplace",
        "athlete_address",
        "athlete_nationality",
        "athlete_sport",
        "athlete_team",
        "athlete_license_number",
        "agent_name",
        "agent_address",
        "agent_registration_id",
    ),
    "duration": (
        "start_date",
        "end_date",
        "contract_duration_months",
        "renewal_terms",
        "termination_date",
        "notice_period_days",
        "event_calendar",
    ),
    "athlete_obligations": (
        "number_of_events",
        "event_types_required",
        "posts_per_month",
        "stories_per_month",
        "video_mentions",
        "hashtags_required",
        "equipment_usage",
        "sector_exclusivity",
        "competitions_mandatory",
        "performance_goals",
        "training_commitment",
        "injury_notification_delay",
    ),
    "organisation_obligations": (
        "equipment_provided",
        "support_logistics",
        "insurance_details",
        "media_exposure",
        "promotion_channels",
        "brand_guidelines",
    ),
    "financials": (
        "amount",
        "currency",
        "payment_schedule",
        "payment_method",
        "bonus_amount",
        "bonus_conditions",
        "royalty_rate",
        "royalty_base",
        "penalty_amount",
    ),
    "intellectual_property": (
        "image_rights_scope",
        "duration_years",
        "territory",
        "media_types_allowed",
        "exclusivity_level",
        "license_transfer_terms",
    ),
}

LIST_PLACEHOLDERS = {
    "event_calendar",
    "hashtags_required",
    "equipment_usage",
    "competitions_mandatory",
    "performance_goals",
    "equipment_provided",
    "support_logistics",
    "promotion_channels",
    "brand_guidelines",
    "media_types_allowed",
    "license_transfer_terms",
}


def default_contract_context() -> dict[str, dict[str, object]]:
    """Return the default contract context payload."""

    context: dict[str, dict[str, object]] = {}
    for section, fields in CONTRACT_CONTEXT_STRUCTURE.items():
        section_values: dict[str, object] = {}
        for field in fields:
            section_values[field] = [] if field in LIST_PLACEHOLDERS else None
        context[section] = section_values
    return context


def merge_contract_context(partial: dict[str, dict[str, object]] | None) -> dict[str, dict[str, object]]:
    """Merge a provided partial context into the default structure."""

    base_context = default_contract_context()
    if not partial:
        return base_context

    merged = deepcopy(base_context)
    for section, values in partial.items():
        if not isinstance(values, dict):
            merged[section] = values
            continue
        section_values = merged.setdefault(section, {})
        for field, value in values.items():
            section_values[field] = value
    return merged


class ClauseTemplate(BaseModel):
    """Reusable clause template supporting versioning and placeholders."""

    class Category(models.TextChoices):
        ADMINISTRATIVE = "administratives", "Administratives"
        OBLIGATIONS = "obligations", "Obligations"
        FINANCE = "finance", "Finance"
        IP = "ip", "IP"
        ETHICS = "ethics", "Ethics"
        CONFIDENTIALITY = "confidentiality", "Confidentialité"
        TERMINATION = "termination", "Résiliation"

    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    placeholders = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "title", "version")

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} (v{self.version})"


class Contract(BaseModel):
    """Represents a sponsorship contract between an organisation and an agent."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        NEGOTIATION = "negotiation", "Negotiation"
        AGREEMENT = "agreement", "Agreement"
        ACTIVE = "active", "Active"
        TERMINATED = "terminated", "Terminated"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    initiated_by = models.ForeignKey(
        Collaborator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_contracts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    title = models.CharField(max_length=255)
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    context = models.JSONField(default=default_contract_context, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} - {self.organisation.name}"


class ContractClause(BaseModel):
    """Instance of a clause attached to a specific contract."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="clauses",
    )
    template = models.ForeignKey(
        ClauseTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clauses",
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_mandatory = models.BooleanField(default=False)
    is_modified = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("contract", "position", "created_at")

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} ({self.contract})"


class ContractRevision(BaseModel):
    """Tracks revisions proposed during negotiations."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="proposed_revisions",
    )
    clauses_changed = models.ManyToManyField(
        ContractClause,
        related_name="revisions",
        blank=True,
    )
    comment = models.TextField(blank=True)
    accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Revision for {self.contract} by {self.proposed_by}"


class ContractFile(BaseModel):
    """Stores the signed PDF export associated with a contract."""

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="file",
    )
    pdf = models.FileField(upload_to="contracts/files/")

    class Meta:
        verbose_name = "Contract file"
        verbose_name_plural = "Contract files"

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"File for {self.contract}"
