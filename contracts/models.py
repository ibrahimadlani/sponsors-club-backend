"""Data models for managing sponsorship contracts and their lifecycle."""

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
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


class ClauseTemplate(BaseModel):
    """Reusable clause template supporting placeholder rendering and versioning."""

    class Category(models.TextChoices):
        ADMINISTRATIVE = "ADMINISTRATIVE", "Administratives"
        OBLIGATIONS = "OBLIGATIONS", "Obligations"
        FINANCE = "FINANCE", "Finance"
        INTELLECTUAL_PROPERTY = "IP", "IP"
        ETHICS = "ETHICS", "Ethics"
        CONFIDENTIALITY = "CONFIDENTIALITY", "Confidentiality"
        TERMINATION = "TERMINATION", "Résiliation"

    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    placeholders = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("category", "title", "version")
        unique_together = ("title", "version")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.title} v{self.version}"


class Contract(BaseModel):
    """Represents an agreement between an organisation and an agent."""

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
        on_delete=models.PROTECT,
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
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    title = models.CharField(max_length=255)
    effective_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)

    # Identification of the parties
    organisation_name = models.CharField(max_length=255, blank=True)
    organisation_legal_name = models.CharField(max_length=255, blank=True)
    organisation_type = models.CharField(max_length=100, blank=True)
    organisation_registration_number = models.CharField(max_length=100, blank=True)
    organisation_tax_id = models.CharField(max_length=100, blank=True)
    organisation_address = models.TextField(blank=True)
    organisation_country = models.CharField(max_length=100, blank=True)
    organisation_representative = models.CharField(max_length=255, blank=True)
    organisation_representative_title = models.CharField(max_length=255, blank=True)
    athlete_name = models.CharField(max_length=255, blank=True)
    athlete_birthdate = models.DateField(blank=True, null=True)
    athlete_birthplace = models.CharField(max_length=255, blank=True)
    athlete_address = models.TextField(blank=True)
    athlete_nationality = models.CharField(max_length=100, blank=True)
    athlete_sport = models.CharField(max_length=100, blank=True)
    athlete_team = models.CharField(max_length=255, blank=True)
    athlete_license_number = models.CharField(max_length=100, blank=True)
    agent_name = models.CharField(max_length=255, blank=True)
    agent_address = models.TextField(blank=True)
    agent_registration_id = models.CharField(max_length=100, blank=True)

    # Duration and schedule
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    contract_duration_months = models.PositiveIntegerField(blank=True, null=True)
    renewal_terms = models.TextField(blank=True)
    termination_date = models.DateField(blank=True, null=True)
    notice_period_days = models.PositiveIntegerField(blank=True, null=True)
    event_calendar = models.JSONField(default=list, blank=True)

    # Athlete obligations
    number_of_events = models.PositiveIntegerField(blank=True, null=True)
    event_types_required = models.JSONField(default=list, blank=True)
    posts_per_month = models.PositiveIntegerField(blank=True, null=True)
    stories_per_month = models.PositiveIntegerField(blank=True, null=True)
    video_mentions = models.PositiveIntegerField(blank=True, null=True)
    hashtags_required = models.JSONField(default=list, blank=True)
    equipment_usage = models.TextField(blank=True)
    sector_exclusivity = models.CharField(max_length=255, blank=True)
    competitions_mandatory = models.JSONField(default=list, blank=True)
    performance_goals = models.TextField(blank=True)
    training_commitment = models.CharField(max_length=255, blank=True)
    injury_notification_delay = models.PositiveIntegerField(blank=True, null=True)

    # Organisation obligations
    equipment_provided = models.TextField(blank=True)
    support_logistics = models.TextField(blank=True)
    insurance_details = models.TextField(blank=True)
    media_exposure = models.TextField(blank=True)
    promotion_channels = models.JSONField(default=list, blank=True)
    brand_guidelines = models.TextField(blank=True)

    # Finance and payments
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    currency = models.CharField(max_length=10, default="EUR")
    payment_schedule = models.TextField(blank=True)
    payment_method = models.CharField(max_length=100, blank=True)
    bonus_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    bonus_conditions = models.TextField(blank=True)
    royalty_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    royalty_base = models.CharField(max_length=255, blank=True)
    penalty_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )

    # Intellectual property and image rights
    image_rights_scope = models.TextField(blank=True)
    duration_years = models.PositiveIntegerField(blank=True, null=True)
    territory = models.CharField(max_length=255, blank=True)
    media_types_allowed = models.JSONField(default=list, blank=True)
    exclusivity_level = models.CharField(max_length=100, blank=True)
    license_transfer_terms = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("organisation", "status"), name="contract_org_status_idx"),
            models.Index(fields=("agent",), name="contract_agent_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"Contract {self.title} ({self.status})"


class ContractClause(BaseModel):
    """Concrete clause bound to a specific contract instance."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="clauses",
    )
    template = models.ForeignKey(
        ClauseTemplate,
        on_delete=models.SET_NULL,
        related_name="contract_clauses",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    position = models.PositiveIntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    is_modified = models.BooleanField(default=False)

    class Meta:
        ordering = ("position", "created_at")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"Clause {self.title} ({self.contract_id})"


class ContractRevision(BaseModel):
    """Represents a revision proposal exchanged during negotiations."""

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

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"Revision {self.id} for {self.contract_id}"


class ContractFile(BaseModel):
    """Stores the signed PDF export of a contract."""

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="file",
    )
    pdf = models.FileField(upload_to="contract_exports/", blank=True, null=True)

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"ContractFile {self.contract_id}"
