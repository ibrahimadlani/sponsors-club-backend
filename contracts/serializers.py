"""Serializers handling contract creation, management, and revisions."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import serializers

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractFile,
    ContractRevision,
    merge_contract_context,
)


class OrganisationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ("id", "name", "country")
        ref_name = "ContractsOrganisationSummary"


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Collaborator
        fields = ("id", "role", "user_email")
        ref_name = "ContractsCollaboratorSummary"


class AgentProfileSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AgentProfile
        fields = ("id", "display_name", "user_email")
        ref_name = "ContractsAgentProfileSummary"


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
        read_only_fields = fields


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
            "position",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "template",
            "is_mandatory",
            "created_at",
            "updated_at",
        )


class ContractFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractFile
        fields = ("id", "pdf", "created_at")
        read_only_fields = fields


class ContractRevisionSerializer(serializers.ModelSerializer):
    proposed_by = serializers.SerializerMethodField()
    clauses_changed = ContractClauseSerializer(many=True, read_only=True)

    class Meta:
        model = ContractRevision
        fields = (
            "id",
            "comment",
            "accepted",
            "proposed_by",
            "clauses_changed",
            "created_at",
        )
        read_only_fields = fields

    def get_proposed_by(self, obj: ContractRevision) -> dict[str, Any]:
        user: User = obj.proposed_by
        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }


class ContractSerializer(serializers.ModelSerializer):
    organisation = OrganisationSummarySerializer(read_only=True)
    agent = AgentProfileSummarySerializer(read_only=True)
    initiated_by = CollaboratorSummarySerializer(read_only=True)
    clauses = ContractClauseSerializer(many=True, read_only=True)
    revisions = ContractRevisionSerializer(many=True, read_only=True)
    file = ContractFileSerializer(read_only=True)

    class Meta:
        model = Contract
        fields = (
            "id",
            "title",
            "organisation",
            "agent",
            "initiated_by",
            "status",
            "effective_date",
            "expiration_date",
            "context",
            "clauses",
            "revisions",
            "file",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organisation",
            "agent",
            "initiated_by",
            "clauses",
            "revisions",
            "file",
            "created_at",
            "updated_at",
        )


class ContractClauseCreateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False)
    content = serializers.CharField(required=False)
    position = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        template_id = attrs.get("template_id")
        template = None
        if template_id:
            template = ClauseTemplate.objects.filter(id=template_id, is_active=True).first()
            if not template:
                raise serializers.ValidationError({"template_id": "Clause template not found."})
            attrs["template"] = template
            attrs.setdefault("title", template.title)
            attrs.setdefault("content", template.content)
        if not attrs.get("title"):
            raise serializers.ValidationError({"title": "A clause title is required."})
        if attrs.get("content") in (None, ""):
            raise serializers.ValidationError({"content": "Clause content cannot be empty."})
        return attrs


class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractClause
        fields = ("title", "content", "position")


class ContractCreateSerializer(serializers.ModelSerializer):
    organisation_id = serializers.UUIDField(write_only=True)
    agent_id = serializers.UUIDField(write_only=True)
    context = serializers.JSONField(required=False)

    class Meta:
        model = Contract
        fields = (
            "title",
            "organisation_id",
            "agent_id",
            "effective_date",
            "expiration_date",
            "context",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context["request"]
        user = request.user
        organisation_id = attrs.pop("organisation_id")
        agent_id = attrs.pop("agent_id")

        organisation = Organisation.objects.filter(id=organisation_id).first()
        if not organisation:
            raise serializers.ValidationError({"organisation_id": "Organisation not found."})

        agent = AgentProfile.objects.filter(id=agent_id).select_related("user").first()
        if not agent:
            raise serializers.ValidationError({"agent_id": "Agent not found."})

        collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=user,
        ).first()
        if not collaborator:
            raise serializers.ValidationError(
                {"organisation_id": "You must be a collaborator of the organisation."}
            )

        attrs["organisation"] = organisation
        attrs["agent"] = agent
        attrs["initiated_by"] = collaborator
        attrs["context"] = merge_contract_context(attrs.get("context"))
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Contract:
        organisation = validated_data.pop("organisation")
        agent = validated_data.pop("agent")
        initiated_by = validated_data.pop("initiated_by")

        contract = Contract.objects.create(
            organisation=organisation,
            agent=agent,
            initiated_by=initiated_by,
            **validated_data,
        )

        mandatory_templates = (
            ClauseTemplate.objects.filter(is_mandatory=True, is_active=True)
            .order_by("category", "title")
            .all()
        )
        clauses = [
            ContractClause(
                contract=contract,
                template=template,
                title=template.title,
                content=template.content,
                is_mandatory=True,
                position=index,
            )
            for index, template in enumerate(mandatory_templates)
        ]
        ContractClause.objects.bulk_create(clauses)
        return contract


class ContractStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Contract.Status.choices)


class ContractRevisionCreateSerializer(serializers.Serializer):
    clause_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False,
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate_clause_ids(self, value: list[str]) -> list[str]:
        contract: Contract = self.context["contract"]
        existing_ids = set(
            contract.clauses.values_list("id", flat=True)
        )
        invalid = [clause_id for clause_id in value if clause_id not in existing_ids]
        if invalid:
            raise serializers.ValidationError(
                {"clause_ids": f"Invalid clause ids: {', '.join(map(str, invalid))}."}
            )
        return value
