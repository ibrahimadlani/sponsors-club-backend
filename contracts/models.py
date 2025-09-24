"""Database models powering the contracts domain.

The module models every step of a sponsorship negotiation, from drafting
clauses to recording legal review and DocuSign status updates. Each model is
kept intentionally lightweight so that service layers and serializers can focus
on workflow rules without duplicating persistence concerns.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract helper adding UUID primary keys and timestamps.

    Attributes:
        id: Deterministic UUID primary key for consistent API identifiers.
        created_at: Timestamp for when the record was first persisted.
        updated_at: Timestamp automatically refreshed on each save.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ClauseTemplate(BaseModel):
    """Reusable clause blueprint that can be attached to contracts.

    Attributes:
        category: Classification used to cluster templates in the UI.
        title: Human-friendly label shown to negotiators.
        content: Templated text that can include ``{{placeholders}}``.
        placeholders: List of placeholder keys expected in the content body.
        is_mandatory: Whether new contracts automatically include the clause.
        version: Version counter so legal can iterate on template wording.
    """

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
    # JSON keeps placeholder hints flexible without forcing a rigid schema.
    placeholders = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("category", "title", "-version")
        unique_together = (("title", "version"),)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} (v{self.version})"


class Contract(BaseModel):
    """Represent a sponsorship contract between an organisation and an agent.

    Attributes:
        organisation: Organisation that owns the sponsorship rights.
        agent: Agent responsible for the athlete's interests.
        initiated_by: Collaborator who created the draft contract.
        status: Current lifecycle state of the contract.
        title: Human-friendly title displayed in listings.
        effective_date: Date the agreement becomes active.
        expiration_date: Date the agreement expires naturally.
        owner_agreed_at: Timestamp when the organisation accepted the draft.
        agent_agreed_at: Timestamp when the agent accepted the draft.
        current_version_number: Incrementing counter for version snapshots.
    """

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
        # Sorting by recency keeps the admin changelist aligned with how staff
        # typically triage active deals.
        indexes = [
            models.Index(
                fields=("organisation", "status"), name="contracts_org_status_idx"
            ),
            models.Index(fields=("agent",), name="contracts_agent_idx"),
        ]
        # Indexes above are tuned for the list endpoint filters (status + org)
        # and the agent dashboard where we pivot on the agent id.

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} ({self.organisation.name})"

    def add_mandatory_clauses(self) -> None:
        """Populate the contract with all mandatory clause templates.

        Returns:
            None: The method operates for its side effects only.
        """

        mandatory_templates = ClauseTemplate.objects.filter(is_mandatory=True)
        for template in mandatory_templates:
            # ``get_or_create`` avoids duplicates if the method is invoked twice
            # (e.g. during a retry of the creation workflow).
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
        """Report whether both parties formally agreed to the contract.

        Returns:
            bool: ``True`` when both timestamps are recorded, ``False`` otherwise.
        """

        return bool(self.owner_agreed_at and self.agent_agreed_at)

    def record_agreement(self, *, owner: bool = False, agent: bool = False) -> bool:
        """Persist an agreement timestamp for the relevant actor.

        Args:
            owner: Whether the organisation accepted the contract.
            agent: Whether the agent accepted the contract.

        Returns:
            bool: ``True`` if a timestamp changed, ``False`` otherwise.
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
            # Only persist the fields that actually changed to avoid clobbering
            # unrelated updates that may happen concurrently.
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
        """Create a new contract version snapshot and bump the counter.

        Args:
            created_by: User who generated the version snapshot.
            source_revision: Revision that triggered the new version, if any.
            notes: Free-form description of what changed.

        Returns:
            ContractVersion: The persisted version record representing the
            snapshot.
        """

        next_number = self.current_version_number + 1
        version = ContractVersion.objects.create(
            contract=self,
            number=next_number,
            created_by=created_by,
            source_revision=source_revision,
            notes=notes,
        )
        self.current_version_number = next_number
        # Persist the increment before returning so subsequent calls stay in sync.
        self.save(update_fields=["current_version_number", "updated_at"])
        return version


class ContractClause(BaseModel):
    """Concrete clause tied to a specific contract instance.

    Attributes:
        contract: Parent contract the clause belongs to.
        template: Optional template that seeded the clause content.
        title: Heading shown in PDFs and the admin interface.
        content: Body of the clause, potentially customised from the template.
        is_mandatory: Whether the clause originated from a mandatory template.
        is_modified: Tracks edits made after the template was applied.
    """

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
    """Record of proposed clause updates during negotiations.

    Attributes:
        contract: Contract impacted by the revision.
        proposed_by: User who suggested the change.
        clauses_changed: Clauses impacted by the proposal.
        comment: Context explaining the proposed changes.
        accepted: Ternary flag representing review outcome.
    """

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
    """Snapshot of the contract at a specific negotiation step.

    Attributes:
        contract: Contract the snapshot belongs to.
        number: Incremental version counter.
        created_by: User who generated the snapshot.
        source_revision: Revision that triggered the snapshot.
        notes: Optional narrative attached to the version.
    """

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
    """Free-form annotation tied to a specific contract version and clause.

    Attributes:
        contract: Contract receiving the comment.
        version: Version that the comment references.
        clause: Clause targeted by the feedback (optional).
        author: User who left the comment.
        body: Content of the annotation.
    """

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
    """Track the legal review lifecycle prior to signature.

    Attributes:
        contract: Contract undergoing review.
        requested_by: Collaborator who requested the review.
        notes: Additional context provided during submission.
        verified_by: Legal reviewer who completed the verification.
        verified_at: Timestamp for the verification action.
        verification_notes: Final comments from the legal reviewer.
    """

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
    """Track DocuSign envelope and signature status.

    Attributes:
        contract: Contract being signed.
        envelope_id: Identifier returned by the external e-sign provider.
        status: Workflow state for the signature process.
        initiated_by: User who started the signing flow.
        last_payload: Latest webhook payload captured for auditing.
        completed_at: Timestamp when the signing reached a terminal state.
    """

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
    """Persist signed contract exports (e.g. PDF).

    Attributes:
        contract: Contract the file belongs to.
        pdf: File handle for the exported document.
    """

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
