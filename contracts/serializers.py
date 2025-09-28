"""Serializers translating contract models to and from API payloads.

The serializers coordinate validation rules shared between the REST views and
admin actions. Inline comments highlight the decisions that ensure the public
API remains predictable for both collaborators and agents.
"""

from typing import Iterable

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User

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

    name = serializers.CharField(source="name", read_only=True)

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
            "created_at",
            "updated_at",
            "clauses",
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


class ContractCreateSerializer(serializers.ModelSerializer):
    """Validate the minimal payload required to open a contract."""

    organisation_id = serializers.UUIDField(write_only=True)
    agent_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Contract
        fields = (
            "organisation_id",
            "agent_id",
            "title",
            "effective_date",
            "expiration_date",
        )

    def validate(self, attrs):
        """Ensure the requester can bind the contract parties.

        Args:
            attrs: Incoming data validated by DRF.

        Returns:
            dict: Mutated attributes with resolved foreign keys.

        Raises:
            serializers.ValidationError: When the organisation or agent is
                missing or the user lacks permissions.
        """

        request = self.context["request"]
        user = request.user
        organisation_id = attrs["organisation_id"]
        agent_id = attrs["agent_id"]

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

        collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=user,
        ).first()
        if collaborator is None:
            raise PermissionDenied("User must be a collaborator of the organisation.")

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

        Args:
            validated_data: Sanitised clause payload.

        Returns:
            ContractClause: Newly created clause instance.
        """

        contract: Contract = self.context["contract"]
        template = validated_data.pop("template", None)
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
        return instance


class ContractStatusSerializer(serializers.Serializer):
    """Validate requested status transitions for a contract."""

    status = serializers.ChoiceField(choices=Contract.Status.choices)


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
