"""Serializers handling contract creation, clauses, and status updates."""

# pylint: disable=missing-class-docstring,too-few-public-methods

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from athletes.models import Athlete
from organisations.models import Collaborator, Organisation
from users.models import AgentProfile

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import collaborator_meets_requirement, requirement_denied_payload

from .models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractStatusHistory,
    ContractVersion,
)


class OrganisationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ('id', 'name', 'country')
        ref_name = 'ContractsOrganisationSummary'


class AgentSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = AgentProfile
        fields = ('id', 'display_name', 'user_email')
        ref_name = 'ContractsAgentSummary'


class AthleteSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Athlete
        fields = ('id', 'full_name', 'sport_id')
        ref_name = 'ContractsAthleteSummary'


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Collaborator
        fields = ('id', 'organisation_id', 'role', 'user_email')
        ref_name = 'ContractsCollaboratorSummary'


class ClauseTemplateSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ClauseTemplate
        fields = ('id', 'identifier', 'title', 'type', 'mandatory', 'version')


class ContractClauseSerializer(serializers.ModelSerializer):
    template = ClauseTemplateSummarySerializer(read_only=True)

    class Meta:
        model = ContractClause
        fields = (
            'id',
            'template',
            'values',
            'order_index',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class ContractStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ContractStatusHistory
        fields = (
            'id',
            'from_status',
            'to_status',
            'changed_by',
            'changed_by_email',
            'changed_at',
            'reason',
        )
        read_only_fields = fields

    def get_changed_by_email(self, obj):
        """Return the email address of the user who performed the change."""

        return getattr(obj.changed_by, 'email', None)


class ContractSerializer(serializers.ModelSerializer):
    organisation = OrganisationSummarySerializer(read_only=True)
    athlete = AthleteSummarySerializer(read_only=True)
    created_by = CollaboratorSummarySerializer(read_only=True)
    clauses = ContractClauseSerializer(many=True, read_only=True)
    status_history = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = (
            'id',
            'organisation',
            'athlete',
            'created_by',
            'status',
            'start_date',
            'end_date',
            'amount',
            'currency',
            'created_at',
            'updated_at',
            'clauses',
            'status_history',
        )
        read_only_fields = fields

    def get_status_history(self, obj):
        """Serialize the status history ordered by most recent first."""

        history = obj.status_history.order_by('-changed_at')  # pylint: disable=no-member
        return ContractStatusHistorySerializer(history, many=True).data


class ContractClauseInputSerializer(serializers.Serializer):
    template_id = serializers.UUIDField()
    order_index = serializers.IntegerField(min_value=0, required=False, default=0)
    values = serializers.JSONField(required=False)

    def create(self, validated_data):  # pylint: disable=unused-argument
        """Disallow DRF from attempting to create instances for input serializer."""

        raise NotImplementedError('ContractClauseInputSerializer is input-only.')

    def update(self, instance, validated_data):  # pylint: disable=unused-argument
        """Disallow DRF from updating instances for input serializer."""

        raise NotImplementedError('ContractClauseInputSerializer is input-only.')


class ContractCreateSerializer(serializers.ModelSerializer):
    organisation_id = serializers.UUIDField(write_only=True)
    athlete_id = serializers.UUIDField(write_only=True)
    clauses = ContractClauseInputSerializer(many=True, required=False)

    class Meta:
        model = Contract
        fields = (
            'organisation_id',
            'athlete_id',
            'start_date',
            'end_date',
            'amount',
            'currency',
            'clauses',
        )

    def validate(self, attrs):
        """Attach foreign key instances and enforce workspace permissions."""

        request = self.context['request']
        user = request.user
        organisation_id = attrs['organisation_id']
        athlete_id = attrs['athlete_id']

        organisation = Organisation.objects.filter(  # pylint: disable=no-member
            id=organisation_id
        ).first()
        if not organisation:
            raise serializers.ValidationError({'organisation_id': 'Organisation not found.'})
        athlete = Athlete.objects.select_related('agent').filter(  # pylint: disable=no-member
            id=athlete_id
        ).first()
        if not athlete:
            raise serializers.ValidationError({'athlete_id': 'Athlete not found.'})

        collaborator = Collaborator.objects.filter(  # pylint: disable=no-member
            organisation=organisation,
            user=user,
        ).first()
        if not collaborator or collaborator.role != Collaborator.Role.OWNER:
            raise PermissionDenied('Only organisation owners may create contracts.')

        requirement = COLLABORATOR_FEATURES['contract_management']
        if not collaborator_meets_requirement(user, requirement):
            payload = requirement_denied_payload(
                requirement,
                'Upgrade required to access the contract workspace.',
            )
            raise PermissionDenied(payload)

        attrs['organisation'] = organisation
        attrs['athlete'] = athlete
        attrs['created_by'] = collaborator
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        organisation = validated_data.pop('organisation')
        athlete = validated_data.pop('athlete')
        created_by = validated_data.pop('created_by')
        clauses_data = validated_data.pop('clauses', [])
        validated_data.pop('organisation_id', None)
        validated_data.pop('athlete_id', None)

        resolved_clauses = []
        for clause_data in clauses_data:
            template = ClauseTemplate.objects.filter(  # pylint: disable=no-member
                id=clause_data['template_id']
            ).first()
            if not template:
                message = f"Clause template {clause_data['template_id']} not found."
                raise serializers.ValidationError({'clauses': message})
            resolved_clauses.append((template, clause_data))

        contract = Contract.objects.create(  # pylint: disable=no-member
            organisation=organisation,
            athlete=athlete,
            created_by=created_by,
            **validated_data,
        )

        for template, clause_data in resolved_clauses:
            ContractClause.objects.create(  # pylint: disable=no-member
                contract=contract,
                template=template,
                values=clause_data.get('values', {}),
                order_index=clause_data.get('order_index', 0),
            )

        return contract


class ContractStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Contract.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):  # pylint: disable=unused-argument
        """Prevent creation; serializer is used only for validation."""

        raise NotImplementedError('ContractStatusUpdateSerializer is read-only.')

    def update(self, instance, validated_data):  # pylint: disable=unused-argument
        """Prevent updates; serializer is used only for validation."""

        raise NotImplementedError('ContractStatusUpdateSerializer is read-only.')


class ContractVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractVersion
        fields = ('id', 'version_number', 'snapshot', 'created_at')
        read_only_fields = fields


class ContractClauseUpsertSerializer(serializers.Serializer):
    template_id = serializers.UUIDField()
    order_index = serializers.IntegerField(min_value=0, required=False, default=0)
    values = serializers.JSONField(required=False)

    def create(self, validated_data):  # pylint: disable=unused-argument
        """Prevent creation attempts for this utility serializer."""

        raise NotImplementedError('ContractClauseUpsertSerializer is utility-only.')

    def update(self, instance, validated_data):  # pylint: disable=unused-argument
        """Prevent update attempts for this utility serializer."""

        raise NotImplementedError('ContractClauseUpsertSerializer is utility-only.')
