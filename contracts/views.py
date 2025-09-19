"""View layer for contract management endpoints."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from organisations.models import Collaborator
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
from .serializers import (
    ContractClauseSerializer,
    ContractClauseUpsertSerializer,
    ContractCreateSerializer,
    ContractSerializer,
    ContractStatusUpdateSerializer,
    ContractVersionSerializer,
)


class ContractPagination(PageNumberPagination):
    """Default pagination for contract listings."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ContractsViewSet(viewsets.GenericViewSet):
    """Expose contract CRUD operations and clause management endpoints."""

    serializer_class = ContractSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ContractPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("status", "organisation", "athlete")

    def get_queryset(self):
        """Return contracts accessible to the current user."""

        if getattr(self, "swagger_fake_view", False):  # pragma: no cover
            return Contract.objects.none()  # pylint: disable=no-member

        user = self.request.user
        base_qs = Contract.objects.select_related(  # pylint: disable=no-member
            "organisation",
            "athlete__sport",
            "created_by__user",
        ).prefetch_related("clauses__template", "status_history")

        if user.is_staff or user.is_superuser:
            return base_qs

        filters = Q()
        collaborator_org_ids = list(
            Collaborator.objects.filter(user=user).values_list(  # pylint: disable=no-member
                "organisation_id", flat=True
            )
        )
        if collaborator_org_ids:
            filters |= Q(organisation_id__in=collaborator_org_ids)
        try:
            agent_profile = user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]  # pylint: disable=no-member
            agent_profile = None
        if agent_profile:
            filters |= Q(athlete__agent=agent_profile)
        if not filters:
            return base_qs.none()
        return base_qs.filter(filters)

    def list(self, _request, *_args, **_kwargs):
        """Return paginated contracts for the requesting user."""

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = ContractSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @transaction.atomic
    def create(self, request, *_args, **_kwargs):
        """Create a new contract and snapshot its initial version."""

        serializer = ContractCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        self._create_version(contract)
        output = ContractSerializer(contract)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def retrieve(self, _request, *_args, **_kwargs):
        """Return a single contract instance."""

        contract = self.get_object()
        serializer = ContractSerializer(contract)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, *_args, **_kwargs):
        """Update a contract's status while recording the change history."""

        contract = self.get_object()
        if not self._user_is_owner(request.user, contract.organisation_id):
            detail = "Only organisation owners can update contract status."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        requirement = COLLABORATOR_FEATURES["contract_management"]
        if not collaborator_meets_requirement(request.user, requirement):
            payload = requirement_denied_payload(
                requirement,
                "Upgrade required to access the contract workspace.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        serializer = ContractStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        if not self._is_valid_transition(contract.status, new_status):
            detail = (
                f"Invalid status transition from {contract.status} to {new_status}."
            )
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        previous_status = contract.status
        if previous_status == new_status:
            return Response(ContractSerializer(contract).data)

        contract.status = new_status
        contract.save(update_fields=["status", "updated_at"])
        ContractStatusHistory.objects.create(  # pylint: disable=no-member
            contract=contract,
            from_status=previous_status,
            to_status=new_status,
            changed_by=request.user,
            reason=reason,
        )
        self._create_version(contract)
        return Response(ContractSerializer(contract).data)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, _request, *_args, **_kwargs):
        """Return the ordered list of contract versions."""

        contract = self.get_object()
        versions_qs = contract.versions.order_by("-version_number")  # pylint: disable=no-member
        serializer = ContractVersionSerializer(versions_qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="clauses")
    @transaction.atomic
    def upsert_clause(self, request, *_args, **_kwargs):  # pylint: disable=too-many-locals
        """Create or update a clause on the contract."""

        contract = self.get_object()
        if not self._user_is_owner(request.user, contract.organisation_id):
            detail = "Only organisation owners can modify clauses."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        requirement = COLLABORATOR_FEATURES["contract_management"]
        if not collaborator_meets_requirement(request.user, requirement):
            payload = requirement_denied_payload(
                requirement,
                "Upgrade required to access the contract workspace.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        serializer = ContractClauseUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template_id = serializer.validated_data["template_id"]
        order_index = serializer.validated_data.get("order_index", 0)
        values = serializer.validated_data.get("values", {})

        template = ClauseTemplate.objects.filter(  # pylint: disable=no-member
            id=template_id
        ).first()
        if not template:
            detail = "Clause template not found."
            return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)

        clause, created = ContractClause.objects.get_or_create(  # pylint: disable=no-member
            contract=contract,
            template=template,
            order_index=order_index,
            defaults={"values": values},
        )
        if not created:
            clause.values = values
            clause.save(update_fields=["values", "updated_at"])

        self._create_version(contract)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ContractClauseSerializer(clause).data, status=status_code)

    @action(detail=True, methods=["post"], url_path="render")
    def render_contract(self, _request, *_args, **_kwargs):
        """Return the rendered contract text with placeholder substitution."""

        contract = self.get_object()
        payload = {
            "contract_id": str(contract.id),
            "rendered_text": self._render_contract_text(contract),
        }
        return Response(payload)

    def _user_is_owner(self, user, organisation_id):
        """Return True when the user owns the organisation or is superuser."""

        is_owner = Collaborator.objects.filter(  # pylint: disable=no-member
            user=user,
            organisation_id=organisation_id,
            role=Collaborator.Role.OWNER,
        ).exists()
        return is_owner or user.is_superuser

    def _is_valid_transition(self, current_status, new_status):
        """Check whether the status transition is allowed by the workflow."""

        workflow = {
            Contract.Status.DRAFT: {
                Contract.Status.AGREEMENT,
                Contract.Status.VERIFICATION,
            },
            Contract.Status.AGREEMENT: {
                Contract.Status.VERIFICATION,
                Contract.Status.DRAFT,
            },
            Contract.Status.VERIFICATION: {
                Contract.Status.ACTIVE,
                Contract.Status.AGREEMENT,
            },
            Contract.Status.ACTIVE: {Contract.Status.TERMINATED},
            Contract.Status.TERMINATED: set(),
        }
        allowed = workflow.get(current_status, set())
        return new_status in allowed

    def _create_version(self, contract):
        """Persist a snapshot of the current contract state."""

        snapshot = self._build_snapshot(contract)
        ContractVersion.objects.create(  # pylint: disable=no-member
            contract=contract,
            snapshot=snapshot,
            version_number=0,
        )

    def _build_snapshot(self, contract):
        """Return a dictionary representing the current contract state."""

        contract.refresh_from_db()
        clauses = contract.clauses.select_related("template").order_by(  # pylint: disable=no-member
            "order_index"
        )
        amount = contract.amount
        amount_value = str(amount) if isinstance(amount, Decimal) else amount
        return {
            "contract": {
                "id": str(contract.id),
                "organisation_id": str(contract.organisation_id),
                "athlete_id": str(contract.athlete_id),
                "status": contract.status,
                "start_date": contract.start_date.isoformat()
                if contract.start_date
                else None,
                "end_date": contract.end_date.isoformat()
                if contract.end_date
                else None,
                "amount": amount_value,
                "currency": contract.currency,
                "updated_at": contract.updated_at.isoformat()
                if contract.updated_at
                else None,
            },
            "clauses": [
                {
                    "id": str(clause.id),
                    "template_id": str(clause.template_id),
                    "template_identifier": clause.template.identifier,  # pylint: disable=no-member
                    "values": clause.values,
                    "order_index": clause.order_index,
                }
                for clause in clauses
            ],
        }

    def _render_contract_text(self, contract):
        """Render contract text by substituting placeholder values."""

        outputs = []
        clauses = contract.clauses.select_related("template").order_by(  # pylint: disable=no-member
            "order_index"
        )
        for clause in clauses:
            template = clause.template
            text = template.content
            placeholders = set(template.placeholders or []) | set(
                (clause.values or {}).keys()
            )
            for placeholder in placeholders:
                default = f"[{placeholder}]"
                value = (
                    clause.values.get(placeholder, default)
                    if clause.values
                    else default
                )
                text = text.replace(f"[{placeholder}]", str(value))
            outputs.append(text.strip())
        return "\n\n".join(filter(None, outputs))
