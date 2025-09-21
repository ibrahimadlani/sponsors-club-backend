"""Database models powering the contracts domain."""

import uuid

from django.conf import settings
from django.db import models

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
        OBLIGATIONS = "obligations", "Obligations"
        FINANCE = "finance", "Finance"
        INTELLECTUAL_PROPERTY = "ip", "IP"
        ETHICS = "ethics", "Ethics"
        CONFIDENTIALITY = "confidentiality", "Confidentiality"
        TERMINATION = "termination", "Résiliation"
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
    effective_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("organisation", "status"), name="contracts_org_status_idx"),
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
