"""Serializers for the contracts API endpoints."""

from typing import Iterable

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User

from .models import ClauseTemplate, Contract, ContractClause, ContractRevision


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
    class Meta:
        model = ClauseTemplate
        fields = (
            "id",
            "category",
            "title",
            "content",
            "placeholders",
            "is_mandatory",
            "version",
        )


class ContractClauseSerializer(serializers.ModelSerializer):
    template = ClauseTemplateSerializer(read_only=True)

    class Meta:
        model = ContractClause
        fields = (
            "id",
            "template",
            "title",
            "content",
            "is_mandatory",
            "is_modified",
        )


class ContractSerializer(serializers.ModelSerializer):
    organisation = OrganisationSummarySerializer(read_only=True)
    agent = AgentSummarySerializer(read_only=True)
    initiated_by = CollaboratorSummarySerializer(read_only=True)
    clauses = ContractClauseSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = (
            "id",
            "organisation",
            "agent",
            "initiated_by",
            "status",
            "title",
            "effective_date",
            "expiration_date",
            "created_at",
            "updated_at",
            "clauses",
        )


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


class ContractClauseCreateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    content = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        template = None
        template_id = attrs.get("template_id")
        if template_id:
            try:
                template = ClauseTemplate.objects.get(id=template_id)
            except ClauseTemplate.DoesNotExist as exc:
                raise serializers.ValidationError({"template_id": "Template not found."}) from exc

        if template and not attrs.get("title"):
            attrs["title"] = template.title
        if template and not attrs.get("content"):
            attrs["content"] = template.content

        if not attrs.get("title"):
            raise serializers.ValidationError({"title": "Title is required."})
        if not attrs.get("content"):
            raise serializers.ValidationError({"content": "Content is required."})

        if template:
            attrs["template"] = template
            attrs["is_mandatory"] = template.is_mandatory
        else:
            attrs["is_mandatory"] = False
        return attrs


class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractClause
        fields = ("title", "content")


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

