"""Serializers translating contract models to and from API payloads.

The serializers coordinate validation rules shared between the REST views and
admin actions. Inline comments highlight the decisions that ensure the public
API remains predictable for both collaborators and agents.
"""

from typing import Iterable, Optional

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User

from athletes.models import Athlete

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractComment,
    ContractCounterpart,
    ContractFile,
    ContractLegalReview,
    ContractRevision,
    ContractSigning,
    ContractVersion,
    ImageRightsScope,
    PerformanceBonus,
)


class OrganisationSummarySerializer(serializers.ModelSerializer):
    """Render a minimal organisation representation.

    Attributes:
        Meta: Declares the fields exposed to API consumers.
    """

    class Meta:
        model = Organisation
        fields = ("id", "name")


class AgentSummarySerializer(serializers.ModelSerializer):
    """Render a minimal agent representation for contract payloads."""

    name = serializers.CharField(read_only=True)

    class Meta:
        model = AgentProfile
        fields = ("id", "name")


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    """Expose collaborator role and email for quick lookups."""

    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Collaborator
        fields = ("id", "role", "user_email")


class ClauseTemplateSerializer(serializers.ModelSerializer):
    """Serialize clause templates with their human-readable labels."""

    category_label = serializers.CharField(
        source="get_category_display", read_only=True
    )

    class Meta:
        model = ClauseTemplate
        fields = (
            "id",
            "category",
            "category_label",
            "title",
            "content",
            "placeholders",
            "is_mandatory",
            "version",
        )


class ContractClauseSerializer(serializers.ModelSerializer):
    """Serialize clauses including their source template when available."""

    template = ClauseTemplateSerializer(read_only=True)
    template_id = serializers.SerializerMethodField()

    class Meta:
        model = ContractClause
        fields = (
            "id",
            "template_id",
            "template",
            "title",
            "content",
            "is_mandatory",
            "is_modified",
        )

    def get_template_id(self, obj):
        """Return the identifier of the linked template.

        Args:
            obj: Clause instance being serialized.

        Returns:
            str | None: Template UUID as a string when available.
        """

        template = obj.template
        return str(template.id) if template else None


class ContractSigningSerializer(serializers.ModelSerializer):
    """Expose signing metadata captured from the e-signature provider."""

    initiated_by_email = serializers.EmailField(
        source="initiated_by.email", read_only=True
    )

    class Meta:
        model = ContractSigning
        fields = (
            "id",
            "envelope_id",
            "status",
            "initiated_by_email",
            "last_payload",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "initiated_by_email",
            "last_payload",
            "completed_at",
            "created_at",
            "updated_at",
        )


class ContractLegalReviewSerializer(serializers.ModelSerializer):
    """Summarise the legal review state and reviewers."""

    requested_by_email = serializers.EmailField(
        source="requested_by.email", read_only=True
    )
    verified_by_email = serializers.EmailField(
        source="verified_by.email", read_only=True
    )

    class Meta:
        model = ContractLegalReview
        fields = (
            "id",
            "notes",
            "requested_by_email",
            "verified_by_email",
            "verified_at",
            "verification_notes",
            "created_at",
            "updated_at",
        )


class ContractVersionSerializer(serializers.ModelSerializer):
    """Render contract versions along with their provenance."""

    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    source_revision_id = serializers.SerializerMethodField()

    class Meta:
        model = ContractVersion
        fields = (
            "id",
            "number",
            "notes",
            "created_by_email",
            "source_revision_id",
            "created_at",
        )

    def get_source_revision_id(self, obj):
        """Return the originating revision identifier if present.

        Args:
            obj: ContractVersion instance being serialized.

        Returns:
            str | None: Revision UUID as a string when linked.
        """

        revision = obj.source_revision
        return str(revision.id) if revision else None


class ContractCommentSerializer(serializers.ModelSerializer):
    """Serialize review comments with author details."""

    author_email = serializers.EmailField(source="author.email", read_only=True)
    clause_id = serializers.SerializerMethodField()

    class Meta:
        model = ContractComment
        fields = (
            "id",
            "body",
            "author_email",
            "clause_id",
            "created_at",
        )

    def get_clause_id(self, obj):
        """Return the clause identifier targeted by the comment.

        Args:
            obj: Comment instance being serialized.

        Returns:
            str | None: Clause UUID as a string when available.
        """

        clause = obj.clause
        return str(clause.id) if clause else None


class ContractCounterpartSerializer(serializers.ModelSerializer):
    """Sérialise une contrepartie de sponsoring avec son libellé lisible."""

    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = ContractCounterpart
        fields = (
            "id",
            "type",
            "type_label",
            "description",
            "estimated_value",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "type_label", "created_at", "updated_at")


class PerformanceBonusSerializer(serializers.ModelSerializer):
    """Sérialise une prime de performance sportive."""

    class Meta:
        model = PerformanceBonus
        fields = (
            "id",
            "trigger_condition",
            "bonus_amount",
            "is_achieved",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ImageRightsScopeSerializer(serializers.ModelSerializer):
    """Sérialise le périmètre de cession du droit à l'image."""

    class Meta:
        model = ImageRightsScope
        fields = (
            "id",
            "territory",
            "duration_months",
            "allowed_media",
            "excludes_club_gear",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ContractSerializer(serializers.ModelSerializer):
    """Return the full contract representation consumed by the UI."""

    organisation = OrganisationSummarySerializer(read_only=True)
    agent = AgentSummarySerializer(read_only=True)
    initiated_by = CollaboratorSummarySerializer(read_only=True)
    clauses = ContractClauseSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    signed_file = serializers.SerializerMethodField()
    legal_review = serializers.SerializerMethodField()
    signing = serializers.SerializerMethodField()
    versions = ContractVersionSerializer(many=True, read_only=True)
    counterparts = ContractCounterpartSerializer(many=True, read_only=True)
    performance_bonuses = PerformanceBonusSerializer(many=True, read_only=True)
    image_rights_scope = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = (
            "id",
            "organisation",
            "agent",
            "initiated_by",
            "status",
            "status_label",
            "title",
            "effective_date",
            "expiration_date",
            "owner_agreed_at",
            "agent_agreed_at",
            "current_version_number",
            # Capacité juridique
            "is_athlete_minor",
            "legal_guardian_name",
            "legal_guardian_email",
            "legal_guardian_agreed_at",
            "requires_escrow_deposit",
            "created_at",
            "updated_at",
            "clauses",
            "counterparts",
            "performance_bonuses",
            "image_rights_scope",
            "signed_file",
            "legal_review",
            "signing",
            "versions",
        )

    def get_signed_file(self, obj):
        """Return metadata about the signed PDF, if any.

        Args:
            obj: Contract instance being serialized.

        Returns:
            dict | None: Minimal file payload or ``None`` when absent.
        """

        try:
            contract_file = obj.file
        except ContractFile.DoesNotExist:  # pragma: no cover - relationship missing
            return None

        return {
            "id": str(contract_file.id),
            "created_at": contract_file.created_at,
            "filename": contract_file.pdf.name.split("/")[-1],
        }

    def get_legal_review(self, obj):
        """Return the serialized legal review when it exists.

        Args:
            obj: Contract instance being serialized.

        Returns:
            dict | None: Serialized legal review payload or ``None``.
        """

        try:
            review = obj.legal_review
        except ContractLegalReview.DoesNotExist:
            return None

        return ContractLegalReviewSerializer(review).data

    def get_signing(self, obj):
        """Return the signing metadata when available.

        Args:
            obj: Contract instance being serialized.

        Returns:
            dict | None: Serialized signing payload or ``None``.
        """

        try:
            signing = obj.signing
        except ContractSigning.DoesNotExist:
            return None

        return ContractSigningSerializer(signing).data

    def get_image_rights_scope(self, obj):
        """Return the image rights scope when defined.

        Args:
            obj: Contract instance being serialized.

        Returns:
            dict | None: Serialized ImageRightsScope or ``None``.
        """

        try:
            scope = obj.image_rights_scope
        except ImageRightsScope.DoesNotExist:
            return None

        return ImageRightsScopeSerializer(scope).data


class ContractCreateSerializer(serializers.ModelSerializer):
    """Validate the minimal payload required to open a contract."""

    organisation_id = serializers.UUIDField(write_only=True)
    agent_id = serializers.UUIDField(write_only=True)
    athlete_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Contract
        fields = (
            "organisation_id",
            "agent_id",
            "athlete_id",
            "title",
            "effective_date",
            "expiration_date",
            "is_athlete_minor",
            "legal_guardian_name",
            "legal_guardian_email",
            "requires_escrow_deposit",
        )
        extra_kwargs = {
            "is_athlete_minor": {"required": False},
            "legal_guardian_name": {"required": False},
            "legal_guardian_email": {"required": False},
            "requires_escrow_deposit": {"required": False},
        }

    def validate(self, attrs):
        """Ensure the requester can bind the contract parties and enforce minority rules.

        Minority detection priority:
        1. If ``athlete_id`` is provided, compute from the athlete's birth_date.
        2. Otherwise, honour the explicit ``is_athlete_minor`` flag.

        When the athlete is identified as a minor, ``legal_guardian_name`` and
        ``legal_guardian_email`` are required (Art. L221-1 Code civil).

        Args:
            attrs: Incoming data validated by DRF.

        Returns:
            dict: Mutated attributes with resolved foreign keys.

        Raises:
            serializers.ValidationError: On invalid IDs, missing permissions,
                or incomplete guardian info for a minor.
        """
        from datetime import date

        request = self.context["request"]
        user = request.user
        organisation_id = attrs["organisation_id"]
        agent_id = attrs["agent_id"]
        athlete_id = attrs.pop("athlete_id", None)

        try:
            organisation = Organisation.objects.get(id=organisation_id)
        except Organisation.DoesNotExist as exc:  # pragma: no cover - defensive
            raise serializers.ValidationError(
                {"organisation_id": "Organisation not found."}
            ) from exc

        try:
            agent = AgentProfile.objects.get(id=agent_id)
        except AgentProfile.DoesNotExist as exc:
            raise serializers.ValidationError({"agent_id": "Agent not found."}) from exc

        if athlete_id is not None:
            try:
                athlete = Athlete.objects.get(id=athlete_id)
            except Athlete.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"athlete_id": "Athlete not found."}
                ) from exc
            attrs["athlete"] = athlete

            # Auto-compute minority from birth_date (Art. 488 Code civil)
            birth = athlete.birth_date
            try:
                majority_date = date(birth.year + 18, birth.month, birth.day)
            except ValueError:
                majority_date = date(birth.year + 18, 3, 1)
            attrs["is_athlete_minor"] = date.today() < majority_date

        collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=user,
        ).first()
        if collaborator is None:
            raise PermissionDenied("User must be a collaborator of the organisation.")

        # Guardian info mandatory when athlete is minor
        if attrs.get("is_athlete_minor"):
            errors = {}
            if not attrs.get("legal_guardian_name"):
                errors["legal_guardian_name"] = (
                    "Obligatoire pour un athlète mineur (Art. L221-1 Code civil)."
                )
            if not attrs.get("legal_guardian_email"):
                errors["legal_guardian_email"] = (
                    "Obligatoire pour un athlète mineur (Art. L221-1 Code civil)."
                )
            if errors:
                raise serializers.ValidationError(errors)

        attrs["organisation"] = organisation
        attrs["agent"] = agent
        attrs["initiated_by"] = collaborator
        return attrs

    def create(self, validated_data):
        """Persist the contract and attach mandatory clauses.

        Args:
            validated_data: Sanitised payload produced by :meth:`validate`.

        Returns:
            Contract: Newly created contract instance.
        """

        organisation = validated_data.pop("organisation")
        agent = validated_data.pop("agent")
        initiated_by = validated_data.pop("initiated_by", None)
        validated_data.pop("organisation_id", None)
        validated_data.pop("agent_id", None)

        contract = Contract.objects.create(
            organisation=organisation,
            agent=agent,
            initiated_by=initiated_by,
            **validated_data,
        )
        contract.add_mandatory_clauses()
        return contract


class ContractClauseCreateSerializer(serializers.ModelSerializer):
    """Handle clause creation while respecting optional templates."""

    template_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractClause
        fields = ("template_id", "title", "content")
        extra_kwargs = {
            "title": {"required": False},
            "content": {"required": False},
        }

    def validate(self, attrs):
        """Resolve the template and enforce basic field requirements.

        Args:
            attrs: Incoming data validated by DRF.

        Returns:
            dict: Mutated attributes ready for persistence.

        Raises:
            serializers.ValidationError: When identifiers are invalid or
                required content is missing.
        """

        template = None
        template_id = attrs.pop("template_id", None)
        if template_id is not None:
            try:
                template = ClauseTemplate.objects.get(id=template_id)
            except ClauseTemplate.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"template_id": "Template not found."}
                ) from exc

        title_provided = "title" in self.initial_data
        content_provided = "content" in self.initial_data

        if template:
            final_title = attrs.get("title") if title_provided else template.title
            final_content = (
                attrs.get("content") if content_provided else template.content
            )
            attrs["title"] = final_title or template.title
            attrs["content"] = final_content or template.content
            attrs["template"] = template
            attrs["is_mandatory"] = template.is_mandatory
            attrs["is_modified"] = (
                title_provided and attrs["title"] != template.title
            ) or (content_provided and attrs["content"] != template.content)
        else:
            if not attrs.get("title"):
                raise serializers.ValidationError({"title": "Title is required."})
            if not attrs.get("content"):
                raise serializers.ValidationError({"content": "Content is required."})
            attrs["is_mandatory"] = False
            attrs["is_modified"] = False
        return attrs

    def create(self, validated_data):
        """Persist the clause under the contract provided in context.

        When a new clause is added, any existing owner/agent agreements are
        automatically revoked. This ensures both parties must re-agree to
        the updated contract terms before proceeding to signature.

        Args:
            validated_data: Sanitised clause payload.

        Returns:
            ContractClause: Newly created clause instance.
        """

        contract: Contract = self.context["contract"]
        template = validated_data.pop("template", None)

        # CRITICAL: Revoke any existing agreements when a clause is added
        # Both parties must re-agree to the updated contract terms
        had_owner_agreement = contract.owner_agreed_at is not None
        had_agent_agreement = contract.agent_agreed_at is not None

        if had_owner_agreement or had_agent_agreement:
            contract.owner_agreed_at = None
            contract.agent_agreed_at = None
            contract.save(
                update_fields=["owner_agreed_at", "agent_agreed_at", "updated_at"]
            )

        return ContractClause.objects.create(
            contract=contract,
            template=template,
            **validated_data,
        )


class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    """Handle clause updates triggered during negotiations."""

    template_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractClause
        fields = ("title", "content", "template_id")

    def validate(self, attrs):
        """Apply template lookups and basic empty-field constraints.

        Args:
            attrs: Incoming data validated by DRF.

        Returns:
            dict: Attributes that can safely update the clause.

        Raises:
            serializers.ValidationError: If the template is unknown or fields
                are blank.
        """

        template_id = attrs.pop("template_id", None)
        if template_id is not None:
            try:
                attrs["template"] = ClauseTemplate.objects.get(id=template_id)
            except ClauseTemplate.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"template_id": "Template not found."}
                ) from exc

        if "title" in attrs and not attrs["title"]:
            raise serializers.ValidationError({"title": "Title cannot be blank."})
        if "content" in attrs and not attrs["content"]:
            raise serializers.ValidationError({"content": "Content cannot be blank."})
        return attrs

    def update(self, instance, validated_data):
        """Apply updates while keeping template flags in sync.

        When a clause is modified, any existing owner/agent agreements are
        automatically revoked. This ensures both parties must re-agree to
        the new contract terms before proceeding to signature.

        Args:
            instance: Clause instance to mutate.
            validated_data: Sanitised clause payload.

        Returns:
            ContractClause: Updated clause instance.
        """

        template = validated_data.pop("template", None)
        title_provided = "title" in self.initial_data
        content_provided = "content" in self.initial_data

        if template is not None:
            instance.template = template
            instance.is_mandatory = template.is_mandatory
            if not title_provided:
                validated_data.setdefault("title", template.title)
            if not content_provided:
                validated_data.setdefault("content", template.content)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        reference_template = instance.template
        if reference_template:
            instance.is_modified = not (
                instance.title == reference_template.title
                and instance.content == reference_template.content
            )
        elif validated_data:
            instance.is_modified = True

        instance.save()

        # CRITICAL: Revoke any existing agreements when clause is modified
        # Both parties must re-agree to the updated contract terms
        contract = instance.contract
        had_owner_agreement = contract.owner_agreed_at is not None
        had_agent_agreement = contract.agent_agreed_at is not None

        if had_owner_agreement or had_agent_agreement:
            contract.owner_agreed_at = None
            contract.agent_agreed_at = None
            contract.save(
                update_fields=["owner_agreed_at", "agent_agreed_at", "updated_at"]
            )

        return instance


class PlaceholderValueSerializer(serializers.Serializer):
    """Validate and update placeholder values for a contract clause.

    Phase 2: Allows parties to fill in template placeholders while respecting
    locked placeholders that cannot be modified by certain parties.
    """

    placeholder_values = serializers.JSONField(required=True)

    def validate_placeholder_values(self, value):
        """Validate placeholder updates against template and locks.

        Args:
            value: Dictionary of placeholder key-value pairs to update.

        Returns:
            Validated placeholder values dictionary.

        Raises:
            serializers.ValidationError: If placeholders are invalid or locked.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("placeholder_values must be a dictionary")

        clause = self.context.get("clause")
        if not clause:
            raise serializers.ValidationError("Clause context is required")

        # Get valid placeholder keys from template
        template_placeholders = []
        if clause.template and clause.template.placeholders:
            # Handle both list of strings and list of dicts
            if isinstance(clause.template.placeholders, list):
                if clause.template.placeholders and isinstance(
                    clause.template.placeholders[0], dict
                ):
                    template_placeholders = [
                        p.get("key")
                        for p in clause.template.placeholders
                        if p.get("key")
                    ]
                else:
                    template_placeholders = clause.template.placeholders

        # Validate each placeholder key
        for key in value.keys():
            # Check if placeholder exists in template (if template is used)
            if template_placeholders and key not in template_placeholders:
                raise serializers.ValidationError(
                    {key: f"Placeholder '{key}' not found in clause template"}
                )

            # Check if placeholder is locked
            if not clause.can_modify_placeholder(key):
                raise serializers.ValidationError(
                    {key: f"Placeholder '{key}' is locked and cannot be modified"}
                )

        # Validate placeholder values are not empty
        for key, val in value.items():
            if val is None or (isinstance(val, str) and not val.strip()):
                raise serializers.ValidationError(
                    {key: f"Placeholder '{key}' cannot have an empty value"}
                )

        return value

    def update(self, instance, validated_data):
        """Update clause placeholder values and revoke agreements if needed.

        Args:
            instance: ContractClause instance to update.
            validated_data: Validated placeholder values.

        Returns:
            Updated ContractClause instance.
        """
        new_values = validated_data["placeholder_values"]

        # Merge with existing values (don't replace, update)
        current_values = instance.placeholder_values or {}
        current_values.update(new_values)
        instance.placeholder_values = current_values
        instance.save(update_fields=["placeholder_values", "updated_at"])

        # CRITICAL: Revoke agreements when placeholders change
        # Both parties must re-agree to the updated contract terms
        contract = instance.contract
        had_owner_agreement = contract.owner_agreed_at is not None
        had_agent_agreement = contract.agent_agreed_at is not None

        if had_owner_agreement or had_agent_agreement:
            contract.owner_agreed_at = None
            contract.agent_agreed_at = None
            contract.save(
                update_fields=["owner_agreed_at", "agent_agreed_at", "updated_at"]
            )

        return instance


class ContractStatusSerializer(serializers.Serializer):
    """Validate requested status transitions for a contract.

    When the target status is ``SIGNING``, enforces that all legal prerequisites
    for a minor athlete are met before allowing the transition.  The contract
    instance must be injected via ``context["contract"]`` by the calling view.
    """

    status = serializers.ChoiceField(choices=Contract.Status.choices)

    def validate(self, attrs):
        contract: "Optional[Contract]" = self.context.get("contract")
        if contract is None:
            return attrs

        if (
            attrs["status"] == Contract.Status.SIGNING
            and contract.compute_minor_status()
        ):
            errors = {}
            if not contract.legal_guardian_name:
                errors["legal_guardian_name"] = (
                    "Obligatoire pour un athlète mineur avant la mise en signature "
                    "(Art. L221-1 Code civil)."
                )
            if not contract.legal_guardian_email:
                errors["legal_guardian_email"] = (
                    "Obligatoire pour un athlète mineur avant la mise en signature "
                    "(Art. L221-1 Code civil)."
                )
            if errors:
                raise serializers.ValidationError(errors)

        return attrs


class ContractRevisionSerializer(serializers.ModelSerializer):
    """Serialize revisions along with the acting user."""

    proposed_by = serializers.SerializerMethodField()
    clauses_changed = ContractClauseSerializer(many=True, read_only=True)

    class Meta:
        model = ContractRevision
        fields = (
            "id",
            "proposed_by",
            "comment",
            "accepted",
            "created_at",
            "clauses_changed",
        )

    def get_proposed_by(self, obj):
        """Return a lightweight representation of the proposing user.

        Args:
            obj: ContractRevision instance being serialized.

        Returns:
            dict: Identifier and email of the user.
        """

        user: User = obj.proposed_by
        return {
            "id": str(user.id),
            "email": user.email,
        }


class ContractRevisionCreateSerializer(serializers.Serializer):
    """Validate payloads used to create revisions."""

    clause_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate_clause_ids(self, value: Iterable[str]):
        """Ensure referenced clauses belong to the contract.

        Args:
            value: Raw list of clause identifiers supplied by the client.

        Returns:
            list: Normalised list of clause IDs that exist on the contract.

        Raises:
            serializers.ValidationError: When unknown clauses are referenced.
        """

        contract: Contract = self.context["contract"]
        clause_ids = set(value)
        existing_ids = set(
            contract.clauses.filter(id__in=clause_ids).values_list("id", flat=True)
        )
        missing = clause_ids - existing_ids
        if missing:
            raise serializers.ValidationError("Invalid clause identifiers provided.")
        return list(existing_ids)


class ContractCommentCreateSerializer(serializers.ModelSerializer):
    """Validate comment creation targeting contract versions."""

    clause_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractComment
        fields = ("body", "clause_id")

    def validate(self, attrs):
        """Resolve the clause and attach it to the validated attributes.

        Args:
            attrs: Incoming data validated by DRF.

        Returns:
            dict: Attributes enriched with the clause relation.

        Raises:
            serializers.ValidationError: When the clause cannot be found.
        """

        contract: Contract = self.context["contract"]
        clause_id = attrs.pop("clause_id", None)
        if clause_id is None:
            attrs["clause"] = None
            return attrs

        try:
            clause = contract.clauses.get(id=clause_id)
        except ContractClause.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"clause_id": "Clause not found."}
            ) from exc

        attrs["clause"] = clause
        return attrs

    def create(self, validated_data):
        """Persist the comment for the targeted contract version.

        Args:
            validated_data: Sanitised comment payload.

        Returns:
            ContractComment: Newly created comment instance.
        """

        contract: Contract = self.context["contract"]
        version: ContractVersion = self.context["version"]
        author: User = self.context["author"]
        return ContractComment.objects.create(
            contract=contract,
            version=version,
            author=author,
            clause=validated_data.get("clause"),
            body=validated_data["body"],
        )


class ContractLegalReviewCreateSerializer(serializers.ModelSerializer):
    """Validate the payload used to request a legal review."""

    class Meta:
        model = ContractLegalReview
        fields = ("notes",)


class ContractLegalReviewVerifySerializer(serializers.Serializer):
    """Validate additional notes supplied during legal verification."""

    verification_notes = serializers.CharField(required=False, allow_blank=True)


class ContractSigningInitSerializer(serializers.Serializer):
    """Validate the minimal payload to start the signing workflow."""

    envelope_id = serializers.CharField(max_length=255)


class ContractSigningWebhookSerializer(serializers.Serializer):
    """Validate webhook notifications coming from the e-signature tool."""

    contract_id = serializers.UUIDField()
    envelope_id = serializers.CharField(max_length=255)
    status = serializers.ChoiceField(choices=ContractSigning.Status.choices)
    payload = serializers.JSONField(required=False)
