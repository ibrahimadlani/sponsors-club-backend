"""View layer exposing the contracts API endpoints."""

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from organisations.models import Collaborator

from .models import ClauseTemplate, Contract, ContractClause, ContractFile, ContractRevision
from .serializers import (
    ClauseTemplateSerializer,
    ContractClauseCreateSerializer,
    ContractClauseSerializer,
    ContractClauseUpdateSerializer,
    ContractCreateSerializer,
    ContractRevisionCreateSerializer,
    ContractRevisionSerializer,
    ContractSerializer,
    ContractStatusSerializer,
)


class ClauseTemplateViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Expose the available clause templates for contract drafting."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ClauseTemplateSerializer
    queryset = ClauseTemplate.objects.all().order_by("category", "title")


class ContractViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Expose the contract workflow through REST endpoints."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ContractSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # pragma: no cover
            return Contract.objects.none()

        user = self.request.user
        queryset = Contract.objects.select_related(
            "organisation",
            "agent__user",
            "initiated_by__user",
        ).prefetch_related("clauses__template", "revisions__clauses_changed")

        if user.is_staff or user.is_superuser:
            return queryset

        filters = Q()
        collaborator_org_ids = Collaborator.objects.filter(user=user).values_list(
            "organisation_id", flat=True
        )
        if collaborator_org_ids:
            filters |= Q(organisation_id__in=collaborator_org_ids)

        agent_profile = getattr(user, "agent_profile", None)
        if agent_profile:
            filters |= Q(agent=agent_profile)

        if not filters:
            return Contract.objects.none()

        return queryset.filter(filters).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return ContractCreateSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = ContractSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        contract = self.get_object()
        serializer = ContractSerializer(contract)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = ContractCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        output = ContractSerializer(contract)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="clauses")
    def add_clause(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._can_edit_clauses(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContractClauseCreateSerializer(
            data=request.data, context={"contract": contract}
        )
        serializer.is_valid(raise_exception=True)
        clause = serializer.save()
        output = ContractClauseSerializer(clause)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="clauses/(?P<clause_id>[^/.]+)")
    def update_clause(self, request, clause_id=None, *args, **kwargs):
        contract = self.get_object()
        clause = self._get_clause(contract, clause_id)

        if not self._can_edit_clauses(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContractClauseUpdateSerializer(
            instance=clause, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        clause = serializer.save()
        output = ContractClauseSerializer(clause)
        return Response(output.data)

    @update_clause.mapping.delete
    def delete_clause(self, request, clause_id=None, *args, **kwargs):
        contract = self.get_object()
        clause = self._get_clause(contract, clause_id)

        if clause.is_mandatory:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not self._can_edit_clauses(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        clause.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="revisions")
    def create_revision(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._can_propose_revision(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContractRevisionCreateSerializer(
            data=request.data, context={"contract": contract}
        )
        serializer.is_valid(raise_exception=True)
        revision = ContractRevision.objects.create(
            contract=contract,
            proposed_by=request.user,
            comment=serializer.validated_data.get("comment", ""),
        )
        clause_ids = serializer.validated_data.get("clause_ids", [])
        if clause_ids:
            clauses = contract.clauses.filter(id__in=clause_ids)
            revision.clauses_changed.add(*clauses)
        output = ContractRevisionSerializer(revision)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="revisions")
    def list_revisions(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)
        revisions = contract.revisions.all()
        serializer = ContractRevisionSerializer(revisions, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="revisions/(?P<revision_id>[^/.]+)/accept",
    )
    def accept_revision(self, request, revision_id=None, *args, **kwargs):
        contract = self.get_object()
        if not self._is_collaborator(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            revision = contract.revisions.get(id=revision_id)
        except ContractRevision.DoesNotExist as exc:
            raise Http404 from exc

        revision.accepted = True
        revision.save(update_fields=["accepted", "updated_at"])
        serializer = ContractRevisionSerializer(revision)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._is_owner(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContractStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        if not self._is_valid_transition(contract.status, new_status):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        contract.status = new_status
        contract.save(update_fields=["status", "updated_at"])
        output = ContractSerializer(contract)
        return Response(output.data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_pdf(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            contract_file = contract.file
        except ContractFile.DoesNotExist as exc:
            raise Http404 from exc

        pdf_file = contract_file.pdf
        if not pdf_file:  # pragma: no cover - defensive
            raise Http404

        pdf_file.open("rb")
        filename = pdf_file.name.split("/")[-1]
        return FileResponse(
            pdf_file, as_attachment=True, filename=filename, content_type="application/pdf"
        )

    def _is_owner(self, user, organisation_id):
        return Collaborator.objects.filter(
            user=user,
            organisation_id=organisation_id,
            role=Collaborator.Role.OWNER,
        ).exists()

    def _is_collaborator(self, user, organisation_id):
        return Collaborator.objects.filter(
            user=user, organisation_id=organisation_id
        ).exists()

    def _user_can_view(self, user, contract):
        if user.is_staff or user.is_superuser:
            return True
        if self._is_collaborator(user, contract.organisation_id):
            return True
        agent_profile = getattr(user, "agent_profile", None)
        return bool(agent_profile and agent_profile == contract.agent)

    def _can_edit_clauses(self, user, contract):
        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return False
        return self._is_collaborator(user, contract.organisation_id)

    def _can_propose_revision(self, user, contract):
        if self._is_collaborator(user, contract.organisation_id):
            return True
        agent_profile = getattr(user, "agent_profile", None)
        return bool(agent_profile and agent_profile == contract.agent)

    def _get_clause(self, contract, clause_id):
        try:
            return contract.clauses.get(id=clause_id)
        except ContractClause.DoesNotExist as exc:
            raise Http404 from exc

    def _is_valid_transition(self, current_status, new_status):
        order = [
            Contract.Status.DRAFT,
            Contract.Status.NEGOTIATION,
            Contract.Status.AGREEMENT,
            Contract.Status.ACTIVE,
            Contract.Status.TERMINATED,
        ]
        try:
            current_index = order.index(current_status)
            new_index = order.index(new_status)
        except ValueError:  # pragma: no cover - defensive
            return False
        return new_index == current_index or new_index == current_index + 1
