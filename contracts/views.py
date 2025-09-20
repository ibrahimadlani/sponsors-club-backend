"""View layer for contract management endpoints."""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import FileResponse
from django.utils.encoding import smart_str
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from organisations.models import Collaborator

from .models import ClauseTemplate, Contract, ContractClause, ContractFile
from .serializers import (
    ContractClauseCreateSerializer,
    ContractClauseSerializer,
    ContractClauseUpdateSerializer,
    ContractCreateSerializer,
    ContractDetailSerializer,
    ContractListSerializer,
    ContractRevisionCreateSerializer,
    ContractRevisionSerializer,
)


class ContractsViewSet(viewsets.ModelViewSet):
    """Expose contract CRUD operations and clause management endpoints."""

    permission_classes = (permissions.IsAuthenticated,)
    queryset = Contract.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("status", "organisation", "agent")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # pragma: no cover
            return Contract.objects.none()

        user = self.request.user
        base_qs = Contract.objects.select_related(
            "organisation",
            "agent__user",
            "initiated_by__user",
        ).prefetch_related("clauses__template", "revisions__clauses_changed")

        if user.is_staff or user.is_superuser:
            return base_qs

        filters = Q()
        collaborator_org_ids = list(
            Collaborator.objects.filter(user=user).values_list("organisation_id", flat=True)
        )
        if collaborator_org_ids:
            filters |= Q(organisation_id__in=collaborator_org_ids)

        try:
            agent_profile = user.agent_profile
        except AttributeError:
            agent_profile = None
        if agent_profile:
            filters |= Q(agent=agent_profile)

        if not filters:
            return base_qs.none()
        return base_qs.filter(filters)

    def get_serializer_class(self):
        if self.action == "list":
            return ContractListSerializer
        if self.action == "create":
            return ContractCreateSerializer
        return ContractDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        self._attach_mandatory_clauses(contract)
        detail = ContractDetailSerializer(contract, context=self.get_serializer_context())
        return Response(detail.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        contract = self.get_object()
        serializer = ContractDetailSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="clauses")
    def add_clause(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._can_edit_clauses(request.user, contract):
            detail = "Clauses can only be managed by collaborators during draft or negotiation."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        serializer = ContractClauseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        clause = ContractClause.objects.create(
            contract=contract,
            template=validated.get("template"),
            title=validated["title"],
            content=validated["content"],
            position=validated.get("position", 0),
            is_mandatory=validated.get("is_mandatory", False),
            is_modified=not validated.get("is_mandatory", False),
        )
        output = ContractClauseSerializer(clause)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="clauses/(?P<clause_pk>[^/.]+)")
    def update_clause(self, request, clause_pk=None, *args, **kwargs):
        contract = self.get_object()
        clause = contract.clauses.filter(pk=clause_pk).first()
        if not clause:
            return Response({"detail": "Clause not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_edit_clauses(request.user, contract):
            detail = "Clauses can only be managed by collaborators during draft or negotiation."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        serializer = ContractClauseUpdateSerializer(clause, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if not clause.is_mandatory:
            clause.is_modified = True
            clause.save(update_fields=["is_modified", "updated_at"])
        output = ContractClauseSerializer(clause)
        return Response(output.data)

    @action(detail=True, methods=["delete"], url_path="clauses/(?P<clause_pk>[^/.]+)")
    def delete_clause(self, request, clause_pk=None, *args, **kwargs):
        contract = self.get_object()
        clause = contract.clauses.filter(pk=clause_pk).first()
        if not clause:
            return Response({"detail": "Clause not found."}, status=status.HTTP_404_NOT_FOUND)
        if clause.is_mandatory:
            return Response(
                {"detail": "Mandatory clauses cannot be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not self._can_edit_clauses(request.user, contract):
            detail = "Clauses can only be managed by collaborators during draft or negotiation."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
        clause.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="revisions")
    def revisions(self, request, *args, **kwargs):
        contract = self.get_object()
        if request.method.lower() == "get":
            serializer = ContractRevisionSerializer(contract.revisions.all(), many=True)
            return Response(serializer.data)

        if not self._can_propose_revision(request.user, contract):
            detail = "Only the assigned agent or collaborators can propose revisions."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        serializer = ContractRevisionCreateSerializer(
            data=request.data,
            context={"contract": contract, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        revision = serializer.save()
        output = ContractRevisionSerializer(revision)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="revisions/(?P<revision_pk>[^/.]+)/accept")
    def accept_revision(self, request, revision_pk=None, *args, **kwargs):
        contract = self.get_object()
        revision = contract.revisions.filter(pk=revision_pk).first()
        if not revision:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._is_collaborator(request.user, contract.organisation_id):
            detail = "Only collaborators can accept revisions."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
        revision.accepted = True
        revision.save(update_fields=["accepted", "updated_at"])
        output = ContractRevisionSerializer(revision)
        return Response(output.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._is_owner(request.user, contract.organisation_id):
            detail = "Only organisation owners can update contract status."
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        if new_status not in Contract.Status.values:
            return Response(
                {"detail": "Invalid status supplied."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not self._is_valid_transition(contract.status, new_status):
            detail = f"Cannot transition from {contract.status} to {new_status}."
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        contract.status = new_status
        contract.save(update_fields=["status", "updated_at"])
        serializer = ContractDetailSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="export")
    def export(self, request, *args, **kwargs):
        contract = self.get_object()
        contract_file = self._ensure_contract_file(contract)
        file_handle = contract_file.pdf
        file_handle.open("rb")
        filename = smart_str(file_handle.name.rsplit("/", 1)[-1])
        response = FileResponse(file_handle, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _is_owner(self, user, organisation_id):
        if user.is_superuser:
            return True
        return Collaborator.objects.filter(
            organisation_id=organisation_id,
            user=user,
            role=Collaborator.Role.OWNER,
        ).exists()

    def _is_collaborator(self, user, organisation_id):
        return Collaborator.objects.filter(
            organisation_id=organisation_id,
            user=user,
        ).exists()

    def _can_edit_clauses(self, user, contract: Contract) -> bool:
        return (
            contract.status in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}
            and self._is_collaborator(user, contract.organisation_id)
        )

    def _can_propose_revision(self, user, contract: Contract) -> bool:
        if self._is_collaborator(user, contract.organisation_id):
            return True
        try:
            return user.agent_profile == contract.agent
        except AttributeError:
            return False

    def _is_valid_transition(self, current_status: str, new_status: str) -> bool:
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

    def _attach_mandatory_clauses(self, contract: Contract) -> None:
        templates = (
            ClauseTemplate.objects.filter(is_mandatory=True)
            .order_by("title", "-version")
        )
        latest_by_title = {}
        for template in templates:
            latest_by_title.setdefault(template.title, template)
        ordered_templates = sorted(
            latest_by_title.values(), key=lambda tpl: (tpl.category, tpl.title)
        )
        for position, template in enumerate(ordered_templates, start=1):
            ContractClause.objects.get_or_create(
                contract=contract,
                template=template,
                defaults={
                    "title": template.title,
                    "content": template.content,
                    "position": position,
                    "is_mandatory": True,
                },
            )

    def _ensure_contract_file(self, contract: Contract) -> ContractFile:
        contract_file, _ = ContractFile.objects.get_or_create(contract=contract)
        if not contract_file.pdf:
            content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
            contract_file.pdf.save(
                f"contract-{contract.id}.pdf",
                ContentFile(content),
                save=True,
            )
        return contract_file
