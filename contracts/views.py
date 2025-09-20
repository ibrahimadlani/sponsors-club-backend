"""Views powering the contract management API."""

from __future__ import annotations

from django.db import models, transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from organisations.models import Collaborator
from users.models import AgentProfile

from .models import Contract, ContractClause, ContractRevision
from .serializers import (
    ContractClauseCreateSerializer,
    ContractClauseSerializer,
    ContractClauseUpdateSerializer,
    ContractCreateSerializer,
    ContractRevisionCreateSerializer,
    ContractRevisionSerializer,
    ContractSerializer,
    ContractStatusUpdateSerializer,
)


class ContractPagination(PageNumberPagination):
    """Pagination used for contract listings."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ContractsViewSet(viewsets.GenericViewSet):
    """Expose REST endpoints for contract management."""

    serializer_class = ContractSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ContractPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # pragma: no cover
            return Contract.objects.none()

        user = self.request.user
        clauses_qs = ContractClause.objects.select_related("template").order_by("position", "created_at")
        revisions_qs = ContractRevision.objects.prefetch_related("clauses_changed__template")
        queryset = (
            Contract.objects.select_related(
                "organisation",
                "agent__user",
                "initiated_by__user",
            )
            .prefetch_related(
                Prefetch("clauses", queryset=clauses_qs),
                Prefetch("revisions", queryset=revisions_qs),
            )
            .order_by("-created_at")
        )

        if user.is_staff or user.is_superuser:
            return queryset

        filters = Q()
        collaborator_org_ids = list(
            Collaborator.objects.filter(user=user).values_list("organisation_id", flat=True)
        )
        if collaborator_org_ids:
            filters |= Q(organisation_id__in=collaborator_org_ids)
        agent_profile = getattr(getattr(user, "agent_profile", None), "id", None)
        if agent_profile:
            filters |= Q(agent_id=agent_profile)
        if not filters:
            return queryset.none()
        return queryset.filter(filters).distinct()

    def list(self, request, *_args, **_kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = ContractSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @transaction.atomic
    def create(self, request, *_args, **_kwargs):
        serializer = ContractCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        output = ContractSerializer(contract)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *_args, **_kwargs):
        contract = self.get_object()
        serializer = ContractSerializer(contract)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="clauses", url_name="add-clause")
    @transaction.atomic
    def add_clause(self, request, pk=None):
        contract = self.get_object()
        collaborator = self._require_collaborator(request.user, contract)
        if not collaborator:
            return self._forbidden_response("Only collaborators may modify clauses.")
        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return self._forbidden_response("Clauses can only be changed during draft or negotiation.")

        serializer = ContractClauseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        template = data.get("template")
        position = data.get("position")
        if position is None:
            position = contract.clauses.aggregate(models.Max("position")).get("position__max") or -1
            position += 1

        clause = ContractClause.objects.create(
            contract=contract,
            template=template,
            title=data["title"],
            content=data["content"],
            is_mandatory=template.is_mandatory if template else False,
            is_modified=bool(template and data["content"] != template.content),
            position=position,
        )
        output = ContractClauseSerializer(clause)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"clauses/(?P<clause_id>[^/.]+)",
        url_name="update-clause",
    )
    @transaction.atomic
    def update_clause(self, request, pk=None, clause_id: str | None = None):
        contract = self.get_object()
        collaborator = self._require_collaborator(request.user, contract)
        if not collaborator:
            return self._forbidden_response("Only collaborators may modify clauses.")
        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return self._forbidden_response("Clauses can only be changed during draft or negotiation.")

        clause = contract.clauses.filter(id=clause_id).first()
        if not clause:
            return Response({"detail": "Clause not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ContractClauseUpdateSerializer(clause, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_clause: ContractClause = serializer.save()
        if clause.template and (
            updated_clause.title != clause.template.title
            or updated_clause.content != clause.template.content
        ):
            updated_clause.is_modified = True
        updated_clause.save(update_fields=["title", "content", "position", "is_modified", "updated_at"])
        return Response(ContractClauseSerializer(updated_clause).data)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"clauses/(?P<clause_id>[^/.]+)",
        url_name="delete-clause",
    )
    @transaction.atomic
    def delete_clause(self, request, pk=None, clause_id: str | None = None):
        contract = self.get_object()
        collaborator = self._require_collaborator(request.user, contract)
        if not collaborator:
            return self._forbidden_response("Only collaborators may modify clauses.")
        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return self._forbidden_response("Clauses can only be changed during draft or negotiation.")

        clause = contract.clauses.filter(id=clause_id).first()
        if not clause:
            return Response({"detail": "Clause not found."}, status=status.HTTP_404_NOT_FOUND)
        if clause.is_mandatory:
            return self._forbidden_response("Mandatory clauses cannot be removed from the contract.")
        clause.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="revisions", url_name="revisions")
    @transaction.atomic
    def revisions(self, request, pk=None):
        contract = self.get_object()
        if request.method == "GET":
            serializer = ContractRevisionSerializer(contract.revisions.all(), many=True)
            return Response(serializer.data)

        if not (
            self._require_collaborator(request.user, contract)
            or self._is_contract_agent(request.user, contract)
        ):
            return self._forbidden_response("Only collaborators or the assigned agent can propose revisions.")

        serializer = ContractRevisionCreateSerializer(
            data=request.data, context={"contract": contract}
        )
        serializer.is_valid(raise_exception=True)
        clause_ids = serializer.validated_data.get("clause_ids", [])
        comment = serializer.validated_data.get("comment", "")

        revision = ContractRevision.objects.create(
            contract=contract,
            proposed_by=request.user,
            comment=comment,
        )
        if clause_ids:
            clauses = list(contract.clauses.filter(id__in=clause_ids))
            revision.clauses_changed.set(clauses)
        if contract.status == Contract.Status.DRAFT:
            contract.status = Contract.Status.NEGOTIATION
            contract.save(update_fields=["status", "updated_at"])
        return Response(ContractRevisionSerializer(revision).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"revisions/(?P<revision_id>[^/.]+)/accept",
        url_name="accept-revision",
    )
    @transaction.atomic
    def accept_revision(self, request, pk=None, revision_id: str | None = None):
        contract = self.get_object()
        collaborator = self._require_collaborator(request.user, contract)
        if not collaborator:
            return self._forbidden_response("Only collaborators may accept revisions.")
        revision = contract.revisions.filter(id=revision_id).first()
        if not revision:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)
        revision.accepted = True
        revision.save(update_fields=["accepted", "updated_at"])
        return Response(ContractRevisionSerializer(revision).data)

    @action(detail=True, methods=["patch"], url_path="status", url_name="update-status")
    @transaction.atomic
    def update_status(self, request, pk=None):
        contract = self.get_object()
        collaborator = self._require_collaborator(request.user, contract)
        if not collaborator or collaborator.role != Collaborator.Role.OWNER:
            return self._forbidden_response("Only organisation owners can change the contract status.")

        serializer = ContractStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        if not self._is_valid_transition(contract.status, new_status):
            detail = f"Invalid status transition from {contract.status} to {new_status}."
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        if contract.status != new_status:
            contract.status = new_status
            contract.save(update_fields=["status", "updated_at"])
        return Response(ContractSerializer(contract).data)

    @action(detail=True, methods=["get"], url_path="export", url_name="export")
    def export(self, request, pk=None):
        contract = self.get_object()
        if not (
            self._require_collaborator(request.user, contract)
            or self._is_contract_agent(request.user, contract)
        ):
            return self._forbidden_response("You do not have access to this contract export.")
        try:
            contract_file = contract.file
        except Contract.file.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
            return Response({"detail": "Contract file not available."}, status=status.HTTP_404_NOT_FOUND)
        file_handle = contract_file.pdf.open("rb")
        filename = contract_file.pdf.name.rsplit("/", maxsplit=1)[-1]
        return FileResponse(file_handle, as_attachment=True, filename=filename)

    def _require_collaborator(self, user, contract: Contract) -> Collaborator | None:
        return Collaborator.objects.filter(
            organisation=contract.organisation,
            user=user,
        ).first()

    def _is_contract_agent(self, user, contract: Contract) -> bool:
        try:
            return user.agent_profile == contract.agent
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
            return False

    def _forbidden_response(self, detail: str) -> Response:
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

    def _is_valid_transition(self, current_status: str, new_status: str) -> bool:
        if current_status == new_status:
            return True
        flow = [
            Contract.Status.DRAFT,
            Contract.Status.NEGOTIATION,
            Contract.Status.AGREEMENT,
            Contract.Status.ACTIVE,
            Contract.Status.TERMINATED,
        ]
        try:
            current_index = flow.index(current_status)
            new_index = flow.index(new_status)
        except ValueError:
            return False
        return new_index == current_index + 1
