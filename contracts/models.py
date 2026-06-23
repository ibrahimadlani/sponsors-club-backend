"""Database models powering the contracts domain.

The module models every step of a sponsorship negotiation, from drafting
clauses to recording legal review and DocuSign status updates. Each model is
kept intentionally lightweight so that service layers and serializers can focus
on workflow rules without duplicating persistence concerns.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
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

    # --- Capacité juridique (Art. L221-1 Code civil) ---
    athlete = models.ForeignKey(
        "athletes.Athlete",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
        help_text="Athlète concerné par ce contrat (permet le calcul automatique de la minorité).",
    )
    is_athlete_minor = models.BooleanField(
        default=False,
        help_text="True si l'athlète est mineur au moment de la signature.",
    )
    legal_guardian_name = models.CharField(max_length=255, blank=True)
    legal_guardian_email = models.EmailField(blank=True)
    legal_guardian_agreed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Horodatage de la co-signature du représentant légal (obligatoire si mineur).",
    )
    requires_escrow_deposit = models.BooleanField(
        default=False,
        help_text=(
            "Dépôt à la Caisse des Dépôts obligatoire pour certains revenus de mineurs "
            "(loi du 19 mai 2015 relative au compte bancaire des mineurs)."
        ),
    )

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

    def compute_minor_status(self) -> bool:
        """Return True if the linked athlete is currently under 18.

        Uses the athlete's birth_date when the FK is populated; otherwise
        falls back to the stored ``is_athlete_minor`` flag.
        The age boundary follows French civil law: majority is reached on the
        anniversary of the 18th birthday (Art. 488 Code civil).
        """
        if self.athlete_id and self.athlete.birth_date:
            from datetime import date

            birth = self.athlete.birth_date
            try:
                majority_date = date(birth.year + 18, birth.month, birth.day)
            except ValueError:
                # 29 février → majorité le 1er mars de l'année non bissextile
                majority_date = date(birth.year + 18, 3, 1)
            return timezone.now().date() < majority_date
        return self.is_athlete_minor

    def validate_signing_eligibility(self) -> None:
        """Raise ValidationError if the contract cannot proceed to signing.

        For minor athletes both guardian name and guardian e-mail must be
        present (Art. L221-1 Code civil; annulation de plein droit de tout
        contrat signé par un mineur seul).

        Raises:
            django.core.exceptions.ValidationError: When guardian information
                is missing for a minor athlete.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        if self.compute_minor_status():
            errors = {}
            if not self.legal_guardian_name:
                errors["legal_guardian_name"] = (
                    "Obligatoire pour un athlète mineur (Art. L221-1 Code civil)."
                )
            if not self.legal_guardian_email:
                errors["legal_guardian_email"] = (
                    "Obligatoire pour un athlète mineur (Art. L221-1 Code civil)."
                )
            if errors:
                raise DjangoValidationError(errors)

    @transaction.atomic
    def generate_platform_fee(self):
        """Compute and persist the marketplace fee for this contract.

        Analyses :class:`ContractCounterpart` records to determine whether the
        deal involves cash (commission model) or only material counterparts
        (fixed-fee model):

        - At least one ``CASH`` counterpart → 10 % of total cash value, with a
          €10.00 floor (``FeeType.CASH_COMMISSION``).
        - Only non-cash counterparts → flat €49.00 fee
          (``FeeType.MATERIAL_FIXED_FEE``).

        Calling this method on a contract that already has a ``PlatformFee``
        updates the amount if counterparts changed (idempotent via
        ``update_or_create``).  The status is only reset to PENDING when the
        fee hasn't been paid yet, so a mid-negotiation counterpart change cannot
        undo a completed payment.

        Returns:
            PlatformFee: The created or refreshed fee record.
        """
        from payments.models import PlatformFee

        counterparts = list(self.counterparts.all())
        cash_total: Decimal = sum(
            (
                c.estimated_value
                for c in counterparts
                if c.type == ContractCounterpart.Type.CASH
            ),
            Decimal("0.00"),
        )

        if cash_total > Decimal("0.00"):
            fee_type = PlatformFee.FeeType.CASH_COMMISSION
            amount_due = max(
                PlatformFee.CASH_COMMISSION_MINIMUM,
                (cash_total * PlatformFee.CASH_COMMISSION_RATE).quantize(
                    Decimal("0.01")
                ),
            )
        else:
            fee_type = PlatformFee.FeeType.MATERIAL_FIXED_FEE
            amount_due = PlatformFee.MATERIAL_FIXED_AMOUNT

        # Only reset to PENDING if the fee hasn't already been collected.
        existing = PlatformFee.objects.filter(contract=self).first()
        safe_status = (
            existing.status
            if existing and existing.status == PlatformFee.Status.PAID
            else PlatformFee.Status.PENDING
        )

        fee, _ = PlatformFee.objects.update_or_create(
            contract=self,
            defaults={
                "fee_type": fee_type,
                "amount_due": amount_due,
                "status": safe_status,
            },
        )
        return fee

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

        # NEW: Automatically capture full snapshot of contract state
        version.capture_snapshot(self)

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
        placeholder_values: Dictionary mapping placeholder keys to their values.
        locked_placeholders: List of placeholder keys that cannot be modified.
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

    # Phase 2: Placeholder management
    placeholder_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Valeurs des placeholders {key: value}",
    )
    locked_placeholders = models.JSONField(
        default=list,
        blank=True,
        help_text="Liste des clés de placeholders non modifiables (protégés)",
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"{self.title} ({self.contract.title})"

    def render_content(self) -> str:
        """Render clause content with placeholders replaced by their values.

        Returns:
            Rendered content with {{placeholder}} replaced by actual values.
        """
        rendered = self.content
        for key, value in self.placeholder_values.items():
            placeholder = f"{{{{{key}}}}}"
            rendered = rendered.replace(placeholder, str(value))
        return rendered

    def can_modify_placeholder(self, placeholder_key: str) -> bool:
        """Check if a specific placeholder can be modified.

        Args:
            placeholder_key: The placeholder key to check.

        Returns:
            True if the placeholder is not locked, False otherwise.
        """
        return placeholder_key not in self.locked_placeholders


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
        clauses_snapshot: Complete snapshot of all clauses at this version.
        agreement_status: Snapshot of agreement status (owner_agreed, agent_agreed).
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

    # NEW: Complete snapshot of contract state
    clauses_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete snapshot of all clauses at this version",
    )
    agreement_status = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of agreement status (owner_agreed, agent_agreed)",
    )

    class Meta:
        ordering = ("-number",)
        unique_together = (("contract", "number"),)

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Version {self.number} of {self.contract.title}"

    def capture_snapshot(self, contract):
        """Capture the complete state of the contract at this moment.

        Args:
            contract: Contract instance to snapshot.

        Returns:
            None: Updates self in place.
        """
        clauses_data = []
        for clause in contract.clauses.all().select_related("template"):
            clause_dict = {
                "id": str(clause.id),
                "title": clause.title,
                "content": clause.content,
                "is_mandatory": clause.is_mandatory,
                "is_modified": clause.is_modified,
                "created_at": clause.created_at.isoformat(),
            }

            if clause.template:
                clause_dict["template"] = {
                    "id": str(clause.template.id),
                    "title": clause.template.title,
                    "category": clause.template.category,
                    "version": clause.template.version,
                }
            else:
                clause_dict["template"] = None

            clauses_data.append(clause_dict)

        self.clauses_snapshot = {
            "contract_title": contract.title,
            "effective_date": (
                contract.effective_date.isoformat() if contract.effective_date else None
            ),
            "expiration_date": (
                contract.expiration_date.isoformat()
                if contract.expiration_date
                else None
            ),
            "status": contract.status,
            "clauses": clauses_data,
            "clause_count": len(clauses_data),
        }

        self.agreement_status = {
            "owner_agreed": bool(contract.owner_agreed_at),
            "owner_agreed_at": (
                contract.owner_agreed_at.isoformat()
                if contract.owner_agreed_at
                else None
            ),
            "agent_agreed": bool(contract.agent_agreed_at),
            "agent_agreed_at": (
                contract.agent_agreed_at.isoformat()
                if contract.agent_agreed_at
                else None
            ),
        }

        self.save(update_fields=["clauses_snapshot", "agreement_status", "updated_at"])


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


class ContractAuditLog(BaseModel):
    """Immutable audit trail of contract lifecycle actions.

    Captures every significant contract operation (create, modify, agree, sign)
    along with the actor, timestamp, IP address, and user agent for full
    auditability. This satisfies French legal requirements for electronic
    contract traceability.

    Attributes:
        contract: The contract this log entry concerns.
        actor: User who performed the action (can be null for system actions).
        action: The type of action performed.
        action_details: JSON payload with action-specific metadata (e.g., clause IDs).
        ip_address: IP address from which the action originated.
        user_agent: Browser/client user agent string.
        timestamp: When the action occurred (indexed for fast queries).
    """

    class Action(models.TextChoices):
        # Contract lifecycle
        CONTRACT_CREATED = "contract_created", "Contract créé"
        CONTRACT_UPDATED = "contract_updated", "Contract mis à jour"
        CONTRACT_DELETED = "contract_deleted", "Contract supprimé"

        # Agreement actions
        OWNER_AGREED = "owner_agreed", "Organisation a accepté"
        OWNER_REVOKED_AGREEMENT = (
            "owner_revoked_agreement",
            "Organisation a révoqué l'accord",
        )
        AGENT_AGREED = "agent_agreed", "Agent a accepté"
        AGENT_REVOKED_AGREEMENT = "agent_revoked_agreement", "Agent a révoqué l'accord"

        # Clause management
        CLAUSE_ADDED = "clause_added", "Clause ajoutée"
        CLAUSE_MODIFIED = "clause_modified", "Clause modifiée"
        CLAUSE_DELETED = "clause_deleted", "Clause supprimée"

        # Revision lifecycle
        REVISION_CREATED = "revision_created", "Révision créée"
        REVISION_ACCEPTED = "revision_accepted", "Révision acceptée"
        REVISION_REJECTED = "revision_rejected", "Révision rejetée"

        # Version management
        VERSION_CREATED = "version_created", "Version créée"

        # Legal workflow
        SUBMITTED_FOR_REVIEW = "submitted_for_review", "Soumis pour révision juridique"
        LEGAL_APPROVED = "legal_approved", "Approuvé par le service juridique"
        LEGAL_REJECTED = "legal_rejected", "Rejeté par le service juridique"

        # Signature
        SIGNATURE_INITIATED = "signature_initiated", "Signature initiée"
        SIGNATURE_COMPLETED = "signature_completed", "Signature complétée"

        # Marketplace billing
        PLATFORM_FEE_GENERATED = "platform_fee_generated", "Invoice générée"
        PLATFORM_FEE_PAID = "platform_fee_paid", "Invoice réglée"

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_audit_logs",
        help_text="User who performed the action (null for system actions)",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    action_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context about the action (clause_id, old/new values, etc.)",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["contract", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        actor_display = self.actor.email if self.actor else "System"
        return f"{actor_display} - {self.get_action_display()} @ {self.timestamp}"


class ContractCounterpart(BaseModel):
    """Nature exacte d'une contrepartie de sponsoring.

    Remplace tout champ de montant global sur le contrat pour distinguer
    clairement le numéraire, les dotations matérielles et les remboursements
    de frais — distinction essentielle pour éviter la requalification en
    contrat de travail par l'URSSAF (circulaire DSS/5B/2003/07).

    Attributes:
        contract: Contrat auquel cette contrepartie est rattachée.
        type: Nature juridique de la contrepartie.
        description: Libellé précis (ex : "3 paires de pointes d'athlétisme").
        estimated_value: Valeur marchande en euros pour déclaration et assurance.
    """

    class Type(models.TextChoices):
        CASH = "cash", "Numéraire"
        EQUIPMENT_DOTATION = "equipment_dotation", "Dotation de matériel"
        EXPENSE_REIMBURSEMENT = "expense_reimbursement", "Remboursement de frais"

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="counterparts",
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    description = models.TextField(
        help_text="Libellé précis de la contrepartie (ex : '3 paires de pointes', 'Frais kilométriques').",
    )
    estimated_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Valeur marchande estimée en euros (pour déclaration fiscale et couverture assurantielle).",
    )

    class Meta:
        ordering = ("type", "created_at")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.get_type_display()} – {self.estimated_value} € ({self.contract.title})"


class PerformanceBonus(BaseModel):
    """Prime conditionnelle liée à un résultat sportif.

    Permet de structurer les primes de performance sans les noyer dans une
    rémunération fixe, évitant ainsi la qualification en salaire variable.

    Attributes:
        contract: Contrat auquel cette prime est rattachée.
        trigger_condition: Condition d'activation (ex : "Qualification aux CDF").
        bonus_amount: Montant ou valeur marchande de la prime en euros.
        is_achieved: True si la condition a été atteinte et la prime versée.
    """

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="performance_bonuses",
    )
    trigger_condition = models.TextField(
        help_text="Condition précise d'activation (ex : 'Top 8 aux Championnats de France').",
    )
    bonus_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Valeur de la prime en euros.",
    )
    is_achieved = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:  # pragma: no cover
        return f"Prime : {self.trigger_condition[:60]} ({self.contract.title})"


class ImageRightsScope(BaseModel):
    """Périmètre strict de la cession du droit à l'image de l'athlète.

    En droit français la cession du droit à l'image doit être délimitée
    avec précision dans le temps, l'espace et les supports (CA Paris, 2 févr.
    2010). Un modèle OneToOne force la rédaction explicite de ce périmètre
    pour chaque contrat.

    Attributes:
        contract: Contrat auquel ce périmètre est rattaché (1-1).
        territory: Zone géographique d'exploitation (ex : "France", "Monde").
        duration_months: Durée d'exploitation après la fin du contrat, en mois.
        allowed_media: Supports autorisés (ex : "Réseaux sociaux, Print, PLV").
        excludes_club_gear: True si l'athlète ne peut pas apparaître en tenue
            de club (fréquent en sport amateur fédéral où le règlement de la
            fédération prime sur les accords individuels).
    """

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="image_rights_scope",
    )
    territory = models.CharField(
        max_length=255,
        help_text="Zone géographique d'exploitation (ex : 'France métropolitaine', 'Monde entier').",
    )
    duration_months = models.PositiveIntegerField(
        help_text="Durée maximale d'exploitation des visuels après la fin du contrat, en mois.",
    )
    allowed_media = models.TextField(
        help_text="Supports autorisés listés explicitement (ex : 'Réseaux sociaux, Print, TV, PLV').",
    )
    excludes_club_gear = models.BooleanField(
        default=False,
        help_text=(
            "L'athlète ne peut pas apparaître en tenue de club pour ce sponsor "
            "(protection vis-à-vis du règlement fédéral)."
        ),
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover
        return f"Droit à l'image – {self.contract.title}"
