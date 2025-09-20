"""Serializers handling contract creation, clause management, and revisions."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile

from .models import ClauseTemplate, Contract, ContractClause, ContractFile, ContractRevision

CONTRACT_PARTY_FIELDS = [
    "organisation_name",
    "organisation_legal_name",
    "organisation_type",
    "organisation_registration_number",
    "organisation_tax_id",
    "organisation_address",
    "organisation_country",
    "organisation_representative",
    "organisation_representative_title",
    "athlete_name",
    "athlete_birthdate",
    "athlete_birthplace",
    "athlete_address",
    "athlete_nationality",
    "athlete_sport",
    "athlete_team",
    "athlete_license_number",
    "agent_name",
    "agent_address",
    "agent_registration_id",
]

CONTRACT_DURATION_FIELDS = [
    "start_date",
    "end_date",
    "contract_duration_months",
    "renewal_terms",
    "termination_date",
    "notice_period_days",
    "event_calendar",
]

CONTRACT_ATHLETE_OBLIGATION_FIELDS = [
    "number_of_events",
    "event_types_required",
    "posts_per_month",
    "stories_per_month",
    "video_mentions",
    "hashtags_required",
    "equipment_usage",
    "sector_exclusivity",
    "competitions_mandatory",
    "performance_goals",
    "training_commitment",
    "injury_notification_delay",
]

CONTRACT_ORGANISATION_FIELDS = [
    "equipment_provided",
    "support_logistics",
    "insurance_details",
    "media_exposure",
    "promotion_channels",
    "brand_guidelines",
]

CONTRACT_FINANCE_FIELDS = [
    "total_amount",
    "currency",
    "payment_schedule",
    "payment_method",
    "bonus_amount",
    "bonus_conditions",
    "royalty_rate",
    "royalty_base",
    "penalty_amount",
]

CONTRACT_IP_FIELDS = [
    "image_rights_scope",
    "duration_years",
    "territory",
    "media_types_allowed",
    "exclusivity_level",
    "license_transfer_terms",
]

CONTRACT_DATA_FIELDS = (
    CONTRACT_PARTY_FIELDS
    + CONTRACT_DURATION_FIELDS
    + CONTRACT_ATHLETE_OBLIGATION_FIELDS
    + CONTRACT_ORGANISATION_FIELDS
    + CONTRACT_FINANCE_FIELDS
    + CONTRACT_IP_FIELDS
)


class OrganisationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ("id", "name", "country")
        ref_name = "ContractsOrganisationSummary"


class AgentSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AgentProfile
        fields = ("id", "display_name", "user_email")
        ref_name = "ContractsAgentSummary"


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Collaborator
        fields = ("id", "organisation_id", "role", "user_email")
        ref_name = "ContractsCollaboratorSummary"


class ClauseTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClauseTemplate
        fields = ("id", "title", "category", "is_mandatory", "version", "placeholders")


class ContractClauseSerializer(serializers.ModelSerializer):
    template = ClauseTemplateSerializer(read_only=True)

    class Meta:
        model = ContractClause
        fields = (
            "id",
            "template",
            "title",
            "content",
            "position",
            "is_mandatory",
            "is_modified",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ContractRevisionSerializer(serializers.ModelSerializer):
    proposed_by_email = serializers.EmailField(source="proposed_by.email", read_only=True)
    clauses_changed = ContractClauseSerializer(many=True, read_only=True)

    class Meta:
        model = ContractRevision
        fields = (
            "id",
            "proposed_by",
            "proposed_by_email",
            "comment",
            "accepted",
            "clauses_changed",
            "created_at",
        )
        read_only_fields = fields


class ContractFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractFile
        fields = ("id", "pdf", "created_at")
        read_only_fields = fields


class ContractDetailSerializer(serializers.ModelSerializer):
    organisation = OrganisationSummarySerializer(read_only=True)
    agent = AgentSummarySerializer(read_only=True)
    initiated_by = CollaboratorSummarySerializer(read_only=True)
    clauses = ContractClauseSerializer(many=True, read_only=True)
    revisions = ContractRevisionSerializer(many=True, read_only=True)
    file = ContractFileSerializer(read_only=True)

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
            *CONTRACT_DATA_FIELDS,
            "created_at",
            "updated_at",
            "clauses",
            "revisions",
            "file",
        )
        read_only_fields = fields


class ContractListSerializer(serializers.ModelSerializer):
    organisation = OrganisationSummarySerializer(read_only=True)
    agent = AgentSummarySerializer(read_only=True)

    class Meta:
        model = Contract
        fields = (
            "id",
            "title",
            "organisation",
            "agent",
            "status",
            "effective_date",
            "expiration_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


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
            *CONTRACT_DATA_FIELDS,
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context["request"]
        user = request.user

        organisation_id = attrs.pop("organisation_id")
        agent_id = attrs.pop("agent_id")

        organisation = Organisation.objects.filter(id=organisation_id).first()
        if not organisation:
            raise serializers.ValidationError({"organisation_id": "Organisation not found."})

        collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=user,
        ).first()
        if not collaborator:
            raise PermissionDenied("You must be a collaborator of the organisation.")

        agent = AgentProfile.objects.filter(id=agent_id).first()
        if not agent:
            raise serializers.ValidationError({"agent_id": "Agent not found."})

        attrs["organisation"] = organisation
        attrs["agent"] = agent
        attrs["initiated_by"] = collaborator
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Contract:
        return Contract.objects.create(**validated_data)


class ContractClauseCreateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)
    content = serializers.CharField(required=False, allow_blank=True)
    position = serializers.IntegerField(required=False, default=0)
    is_mandatory = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        template = None
        template_id = attrs.get("template_id")
        if template_id:
            template = ClauseTemplate.objects.filter(id=template_id).first()
            if not template:
                raise serializers.ValidationError({"template_id": "Clause template not found."})
            attrs.setdefault("title", template.title)
            attrs.setdefault("content", template.content)
            attrs.setdefault("is_mandatory", template.is_mandatory)
            attrs["template"] = template
        if not attrs.get("title"):
            raise serializers.ValidationError({"title": "This field is required."})
        if not attrs.get("content"):
            raise serializers.ValidationError({"content": "This field is required."})
        return attrs


class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractClause
        fields = ("title", "content", "position")


class ContractRevisionCreateSerializer(serializers.Serializer):
    clauses = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data: dict[str, Any]) -> ContractRevision:
        contract: Contract = self.context["contract"]
        request = self.context["request"]
        revision = ContractRevision.objects.create(
            contract=contract,
            proposed_by=request.user,
            comment=validated_data.get("comment", ""),
        )
        clause_ids = validated_data.get("clauses", [])
        if clause_ids:
            clauses = contract.clauses.filter(id__in=clause_ids)
            revision.clauses_changed.set(clauses)
        return revision
