"""Database models powering the contracts domain."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract helper adding UUID primary keys and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ClauseTemplate(BaseModel):
    """Reusable clause blueprint that can be attached to contracts."""

    class Category(models.TextChoices):
        LEGAL_OBLIGATIONS = "legal_obligations", "Obligatoires (juridiques)"
        FINANCIAL = "financial", "Financières"
        ATHLETE_OBLIGATIONS = "athlete_obligations", "Obligations de l’athlète"
        ORGANISATION_OBLIGATIONS = (
            "organisation_obligations",
            "Obligations de l’organisation",
        )
        INTELLECTUAL_PROPERTY = "intellectual_property", "Propriété intellectuelle"
        CONFIDENTIALITY = "confidentiality", "Confidentialité"
        PERFORMANCE = "performance", "Performance"
        ETHICS_AND_MORALITY = "ethics_morality", "Éthique et moralité"
        LOGISTICS = "logistics", "Logistique"
        ADMINISTRATIVE = "administrative", "Administratives"

    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=255)
    content = models.TextField(
        help_text="Supports placeholders using double curly braces like {{athlete_name}}",
    )
    placeholders = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("category", "title", "-version")
        unique_together = (("title", "version"),)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} (v{self.version})"


class Contract(BaseModel):
    """Represents a sponsorship contract between an organisation and an agent."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        NEGOTIATION = "negotiation", "Negotiation"
        AGREEMENT = "agreement", "Agreement"
        LEGAL_REVIEW = "legal_review", "Legal review"
        SIGNING = "signing", "Signing"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
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
    effective_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    owner_agreed_at = models.DateTimeField(null=True, blank=True)
    agent_agreed_at = models.DateTimeField(null=True, blank=True)
    current_version_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("organisation", "status"), name="contracts_org_status_idx"
            ),
            models.Index(fields=("agent",), name="contracts_agent_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} ({self.organisation.name})"

    def add_mandatory_clauses(self) -> None:
        """Populate the contract with all mandatory clause templates."""

        mandatory_templates = ClauseTemplate.objects.filter(is_mandatory=True)
        for template in mandatory_templates:
            ContractClause.objects.get_or_create(
                contract=self,
                template=template,
                defaults={
                    "title": template.title,
                    "content": template.content,
                    "is_mandatory": True,
                    "is_modified": False,
                },
            )

    def has_full_agreement(self) -> bool:
        """Return whether both parties formally agreed."""

        return bool(self.owner_agreed_at and self.agent_agreed_at)

    def record_agreement(self, *, owner: bool = False, agent: bool = False) -> bool:
        """Persist an agreement timestamp for the relevant actor.

        Returns ``True`` if any timestamp changed.
        """

        changed = False
        now = timezone.now()

        if owner and not self.owner_agreed_at:
            self.owner_agreed_at = now
            changed = True

        if agent and not self.agent_agreed_at:
            self.agent_agreed_at = now
            changed = True

        if changed:
            self.save(
                update_fields=[
                    "owner_agreed_at",
                    "agent_agreed_at",
                    "updated_at",
                ]
            )

        return changed

    def bump_version(
        self,
        *,
        created_by,
        source_revision=None,
        notes: str = "",
    ):
        """Create a new contract version snapshot and bump the counter."""

        next_number = self.current_version_number + 1
        version = ContractVersion.objects.create(
            contract=self,
            number=next_number,
            created_by=created_by,
            source_revision=source_revision,
            notes=notes,
        )
        self.current_version_number = next_number
        self.save(update_fields=["current_version_number", "updated_at"])
        return version


class ContractClause(BaseModel):
    """Concrete clause tied to a specific contract instance."""

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
        related_name="contract_clauses",
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_mandatory = models.BooleanField(default=False)
    is_modified = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} ({self.contract.title})"


class ContractRevision(BaseModel):
    """Record of proposed clause updates during negotiations."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contract_revisions",
    )
    clauses_changed = models.ManyToManyField(
        ContractClause,
        related_name="revisions",
        blank=True,
    )
    comment = models.TextField(blank=True)
    accepted = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Revision {self.id} on {self.contract.title}"


class ContractVersion(BaseModel):
    """Snapshot of the contract at a specific negotiation step."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    number = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_contract_versions",
    )
    source_revision = models.ForeignKey(
        "ContractRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resulting_versions",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-number",)
        unique_together = (("contract", "number"),)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Version {self.number} of {self.contract.title}"


class ContractComment(BaseModel):
    """Free-form annotation tied to a specific contract version and clause."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    clause = models.ForeignKey(
        ContractClause,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contract_comments",
    )
    body = models.TextField()

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Comment by {self.author} on {self.contract.title}"


class ContractLegalReview(BaseModel):
    """Track the legal review lifecycle prior to signature."""

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="legal_review",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requested_contract_reviews",
    )
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_contract_reviews",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Legal review for {self.contract.title}"


class ContractSigning(BaseModel):
    """Track DocuSign envelope and signature status."""

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined"
        ERROR = "error", "Error"

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="signing",
    )
    envelope_id = models.CharField(max_length=255)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.INITIATED,
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="initiated_contract_signings",
    )
    last_payload = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Signing for {self.contract.title}"


class ContractFile(BaseModel):
    """Persist signed contract exports (e.g. PDF)."""

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="file",
    )
    pdf = models.FileField(upload_to="contracts/exports/")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"File for {self.contract.title}"
