"""Serializers for the contracts API endpoints."""

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
    class Meta:
        model = Organisation
        fields = ("id", "name")


class AgentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ("id", "display_name")


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Collaborator
        fields = ("id", "role", "user_email")


class ClauseTemplateSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

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
        template = obj.template
        return str(template.id) if template else None


class ContractSigningSerializer(serializers.ModelSerializer):
    initiated_by_email = serializers.EmailField(source="initiated_by.email", read_only=True)

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
    requested_by_email = serializers.EmailField(source="requested_by.email", read_only=True)
    verified_by_email = serializers.EmailField(source="verified_by.email", read_only=True)

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
        revision = obj.source_revision
        return str(revision.id) if revision else None


class ContractCommentSerializer(serializers.ModelSerializer):
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
        clause = obj.clause
        return str(clause.id) if clause else None


class ContractSerializer(serializers.ModelSerializer):
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
        try:
            review = obj.legal_review
        except ContractLegalReview.DoesNotExist:
            return None

        return ContractLegalReviewSerializer(review).data

    def get_signing(self, obj):
        try:
            signing = obj.signing
        except ContractSigning.DoesNotExist:
            return None

        return ContractSigningSerializer(signing).data


class ContractCreateSerializer(serializers.ModelSerializer):
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
        request = self.context["request"]
        user = request.user
        organisation_id = attrs["organisation_id"]
        agent_id = attrs["agent_id"]

        try:
            organisation = Organisation.objects.get(id=organisation_id)
        except Organisation.DoesNotExist as exc:  # pragma: no cover - defensive
            raise serializers.ValidationError({"organisation_id": "Organisation not found."}) from exc

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
    template_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractClause
        fields = ("template_id", "title", "content")
        extra_kwargs = {
            "title": {"required": False},
            "content": {"required": False},
        }

    def validate(self, attrs):
        template = None
        template_id = attrs.pop("template_id", None)
        if template_id is not None:
            try:
                template = ClauseTemplate.objects.get(id=template_id)
            except ClauseTemplate.DoesNotExist as exc:
                raise serializers.ValidationError({"template_id": "Template not found."}) from exc

        title_provided = "title" in self.initial_data
        content_provided = "content" in self.initial_data

        if template:
            final_title = attrs.get("title") if title_provided else template.title
            final_content = attrs.get("content") if content_provided else template.content
            attrs["title"] = final_title or template.title
            attrs["content"] = final_content or template.content
            attrs["template"] = template
            attrs["is_mandatory"] = template.is_mandatory
            attrs["is_modified"] = (
                (title_provided and attrs["title"] != template.title)
                or (content_provided and attrs["content"] != template.content)
            )
        else:
            if not attrs.get("title"):
                raise serializers.ValidationError({"title": "Title is required."})
            if not attrs.get("content"):
                raise serializers.ValidationError({"content": "Content is required."})
            attrs["is_mandatory"] = False
            attrs["is_modified"] = False
        return attrs

    def create(self, validated_data):
        contract: Contract = self.context["contract"]
        template = validated_data.pop("template", None)
        return ContractClause.objects.create(
            contract=contract,
            template=template,
            **validated_data,
        )


class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    template_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractClause
        fields = ("title", "content", "template_id")

    def validate(self, attrs):
        template_id = attrs.pop("template_id", None)
        if template_id is not None:
            try:
                attrs["template"] = ClauseTemplate.objects.get(id=template_id)
            except ClauseTemplate.DoesNotExist as exc:
                raise serializers.ValidationError({"template_id": "Template not found."}) from exc

        if "title" in attrs and not attrs["title"]:
            raise serializers.ValidationError({"title": "Title cannot be blank."})
        if "content" in attrs and not attrs["content"]:
            raise serializers.ValidationError({"content": "Content cannot be blank."})
        return attrs

    def update(self, instance, validated_data):
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
    status = serializers.ChoiceField(choices=Contract.Status.choices)


class ContractRevisionSerializer(serializers.ModelSerializer):
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
        user: User = obj.proposed_by
        return {
            "id": str(user.id),
            "email": user.email,
        }


class ContractRevisionCreateSerializer(serializers.Serializer):
    clause_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate_clause_ids(self, value: Iterable[str]):
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
    clause_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = ContractComment
        fields = ("body", "clause_id")

    def validate(self, attrs):
        contract: Contract = self.context["contract"]
        clause_id = attrs.pop("clause_id", None)
        if clause_id is None:
            attrs["clause"] = None
            return attrs

        try:
            clause = contract.clauses.get(id=clause_id)
        except ContractClause.DoesNotExist as exc:
            raise serializers.ValidationError({"clause_id": "Clause not found."}) from exc

        attrs["clause"] = clause
        return attrs

    def create(self, validated_data):
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
    class Meta:
        model = ContractLegalReview
        fields = ("notes",)


class ContractLegalReviewVerifySerializer(serializers.Serializer):
    verification_notes = serializers.CharField(required=False, allow_blank=True)


class ContractSigningInitSerializer(serializers.Serializer):
    envelope_id = serializers.CharField(max_length=255)


class ContractSigningWebhookSerializer(serializers.Serializer):
    contract_id = serializers.UUIDField()
    envelope_id = serializers.CharField(max_length=255)
    status = serializers.ChoiceField(choices=ContractSigning.Status.choices)
    payload = serializers.JSONField(required=False)

