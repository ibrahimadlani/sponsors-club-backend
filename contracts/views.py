"""View layer exposing the contracts API endpoints."""

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from organisations.models import Collaborator
from users.models import AgentProfile

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
from .serializers import (
    ClauseTemplateSerializer,
    ContractClauseCreateSerializer,
    ContractClauseSerializer,
    ContractClauseUpdateSerializer,
    ContractCreateSerializer,
    ContractCommentCreateSerializer,
    ContractCommentSerializer,
    ContractLegalReviewCreateSerializer,
    ContractLegalReviewSerializer,
    ContractLegalReviewVerifySerializer,
    ContractRevisionCreateSerializer,
    ContractRevisionSerializer,
    ContractSerializer,
    ContractStatusSerializer,
    ContractSigningInitSerializer,
    ContractSigningSerializer,
    ContractSigningWebhookSerializer,
    ContractVersionSerializer,
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
        queryset = (
            Contract.objects.select_related(
                "organisation",
                "agent__user",
                "initiated_by__user",
                "legal_review",
                "signing",
            )
            .prefetch_related(
                "clauses__template",
                "revisions__clauses_changed",
                Prefetch(
                    "versions",
                    queryset=ContractVersion.objects.order_by("number"),
                ),
                Prefetch(
                    "comments",
                    queryset=ContractComment.objects.select_related("author", "clause", "version"),
                ),
            )
        )

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
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        contract = self.get_object()
        serializer = self.get_serializer(contract)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = ContractCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        contract.bump_version(created_by=request.user, notes="Initial version")
        contract.refresh_from_db()
        output = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="options")
    def options(self, request, *args, **kwargs):
        """Return helper metadata used by the proof-of-concept UI."""

        collaborator_entries = (
            Collaborator.objects.filter(user=request.user)
            .select_related("organisation")
            .order_by("organisation__name")
        )

        organisations = []
        seen = set()
        for collaborator in collaborator_entries:
            organisation = collaborator.organisation
            if organisation.id in seen:
                continue
            organisations.append({"id": str(organisation.id), "name": organisation.name})
            seen.add(organisation.id)

        agents = [
            {"id": str(agent.id), "display_name": agent.display_name}
            for agent in AgentProfile.objects.all().order_by("display_name")
        ]

        statuses = [
            {"value": value, "label": label}
            for value, label in Contract.Status.choices
        ]

        return Response(
            {
                "organisations": organisations,
                "agents": agents,
                "statuses": statuses,
            }
        )

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

        if revision.accepted:
            serializer = ContractRevisionSerializer(revision)
            return Response(serializer.data)

        revision.accepted = True
        revision.save(update_fields=["accepted", "updated_at"])
        contract.bump_version(
            created_by=request.user,
            source_revision=revision,
            notes=revision.comment or "",
        )
        contract.refresh_from_db()
        serializer = ContractRevisionSerializer(revision)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="agree")
    def agree(self, request, *args, **kwargs):
        contract = self.get_object()
        user = request.user

        is_owner = self._is_owner(user, contract.organisation_id)
        agent_profile = getattr(user, "agent_profile", None)
        is_agent = bool(agent_profile and agent_profile == contract.agent)

        if not (is_owner or is_agent):
            return Response(status=status.HTTP_403_FORBIDDEN)

        if contract.status not in {
            Contract.Status.NEGOTIATION,
            Contract.Status.AGREEMENT,
        }:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        contract.record_agreement(owner=is_owner, agent=is_agent)

        if contract.has_full_agreement() and contract.status == Contract.Status.NEGOTIATION:
            contract.status = Contract.Status.AGREEMENT
            contract.save(update_fields=["status", "updated_at"])

        contract.refresh_from_db()
        serializer = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="legal/review")
    def create_legal_review(self, request, *args, **kwargs):
        contract = self.get_object()

        if not self._is_owner(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        if not contract.has_full_agreement():
            return Response(
                {"detail": "Both parties must agree before legal review."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if contract.status not in {
            Contract.Status.AGREEMENT,
            Contract.Status.NEGOTIATION,
        }:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            contract.legal_review
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except ContractLegalReview.DoesNotExist:
            pass

        serializer = ContractLegalReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review = ContractLegalReview.objects.create(
            contract=contract,
            requested_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        contract.status = Contract.Status.LEGAL_REVIEW
        contract.save(update_fields=["status", "updated_at"])
        output = ContractLegalReviewSerializer(review)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="legal/verify")
    def verify_legal_review(self, request, *args, **kwargs):
        contract = self.get_object()

        if not (request.user.is_staff or request.user.is_superuser):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            review = contract.legal_review
        except ContractLegalReview.DoesNotExist as exc:
            raise Http404 from exc

        if contract.status != Contract.Status.LEGAL_REVIEW:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        serializer = ContractLegalReviewVerifySerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        review.verified_by = request.user
        review.verified_at = timezone.now()
        review.verification_notes = serializer.validated_data.get("verification_notes", "")
        review.save(update_fields=["verified_by", "verified_at", "verification_notes", "updated_at"])

        contract.status = Contract.Status.SIGNING
        contract.save(update_fields=["status", "updated_at"])

        output = ContractLegalReviewSerializer(review)
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="signing/init")
    def init_signing(self, request, *args, **kwargs):
        contract = self.get_object()

        if not self._is_owner(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        if contract.status != Contract.Status.SIGNING:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        serializer = ContractSigningInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        signing, created = ContractSigning.objects.update_or_create(
            contract=contract,
            defaults={
                "envelope_id": serializer.validated_data["envelope_id"],
                "initiated_by": request.user,
                "status": ContractSigning.Status.INITIATED,
                "last_payload": {},
                "completed_at": None,
            },
        )

        output = ContractSigningSerializer(signing)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(output.data, status=http_status)

    @action(detail=True, methods=["get"], url_path="signing/status")
    def signing_status(self, request, *args, **kwargs):
        contract = self.get_object()
        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            signing = contract.signing
        except ContractSigning.DoesNotExist as exc:
            raise Http404 from exc

        serializer = ContractSigningSerializer(signing)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="signing/webhook",
        permission_classes=[AllowAny],
    )
    def signing_webhook(self, request, *args, **kwargs):
        serializer = ContractSigningWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            contract = Contract.objects.get(id=serializer.validated_data["contract_id"])
        except Contract.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            signing = contract.signing
        except ContractSigning.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if signing.envelope_id != serializer.validated_data["envelope_id"]:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        signing.status = serializer.validated_data["status"]
        signing.last_payload = serializer.validated_data.get("payload", {})

        if signing.status in {
            ContractSigning.Status.COMPLETED,
            ContractSigning.Status.DECLINED,
            ContractSigning.Status.ERROR,
        }:
            signing.completed_at = timezone.now()

        signing.save(update_fields=["status", "last_payload", "completed_at", "updated_at"])

        if signing.status == ContractSigning.Status.COMPLETED:
            contract.status = Contract.Status.ACTIVE
            contract.save(update_fields=["status", "updated_at"])
        elif signing.status == ContractSigning.Status.DECLINED:
            contract.status = Contract.Status.NEGOTIATION
            contract.save(update_fields=["status", "updated_at"])

        return Response(ContractSigningSerializer(signing).data)

    @action(detail=True, methods=["post"], url_path="expire")
    def expire(self, request, *args, **kwargs):
        contract = self.get_object()

        if not (request.user.is_staff or request.user.is_superuser):
            return Response(status=status.HTTP_403_FORBIDDEN)

        contract.status = Contract.Status.EXPIRED
        contract.save(update_fields=["status", "updated_at"])

        serializer = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="versions")
    def list_versions(self, request, *args, **kwargs):
        contract = self.get_object()

        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        versions = contract.versions.all().order_by("number")
        serializer = ContractVersionSerializer(versions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="versions/(?P<version_id>[^/.]+)/comments")
    def version_comments(self, request, version_id=None, *args, **kwargs):
        contract = self.get_object()

        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        version = self._get_version(contract, version_id)

        if request.method.lower() == "get":
            comments = version.comments.select_related("author", "clause").all()
            serializer = ContractCommentSerializer(comments, many=True)
            return Response(serializer.data)

        serializer = ContractCommentCreateSerializer(
            data=request.data,
            context={
                "contract": contract,
                "version": version,
                "author": request.user,
            },
        )
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        output = ContractCommentSerializer(comment)
        return Response(output.data, status=status.HTTP_201_CREATED)

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

    def _get_version(self, contract, version_id):
        try:
            return contract.versions.get(id=version_id)
        except ContractVersion.DoesNotExist as exc:
            raise Http404 from exc

    def _is_valid_transition(self, current_status, new_status):
        transitions = {
            Contract.Status.DRAFT: {
                Contract.Status.DRAFT,
                Contract.Status.NEGOTIATION,
            },
            Contract.Status.NEGOTIATION: {
                Contract.Status.NEGOTIATION,
                Contract.Status.AGREEMENT,
            },
            Contract.Status.AGREEMENT: {
                Contract.Status.AGREEMENT,
                Contract.Status.LEGAL_REVIEW,
            },
            Contract.Status.LEGAL_REVIEW: {
                Contract.Status.LEGAL_REVIEW,
                Contract.Status.SIGNING,
            },
            Contract.Status.SIGNING: {
                Contract.Status.SIGNING,
                Contract.Status.ACTIVE,
                Contract.Status.NEGOTIATION,
            },
            Contract.Status.ACTIVE: {
                Contract.Status.ACTIVE,
                Contract.Status.EXPIRED,
                Contract.Status.TERMINATED,
            },
            Contract.Status.EXPIRED: {
                Contract.Status.EXPIRED,
                Contract.Status.TERMINATED,
            },
            Contract.Status.TERMINATED: {Contract.Status.TERMINATED},
        }

        allowed = transitions.get(current_status, set())
        return new_status in allowed
