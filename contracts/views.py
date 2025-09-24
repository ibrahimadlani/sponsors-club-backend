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

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import collaborator_meets_requirement, requirement_denied_payload
from core.responses import error_response

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
    """Expose the available clause templates for contract drafting.

    Attributes:
        permission_classes: Authentication requirement for listing templates.
        serializer_class: Serializer used to render templates.
        queryset: Base queryset ordered for predictable UI grouping.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = ClauseTemplateSerializer
    queryset = ClauseTemplate.objects.all().order_by("category", "title")


class ContractViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Expose the contract workflow through REST endpoints.

    Attributes:
        permission_classes: Guards the viewset behind authentication.
        serializer_class: Default serializer used for contract retrieval.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = ContractSerializer

    def get_queryset(self):
        """Return the base queryset tailored to the requesting user.

        Returns:
            QuerySet: Contracts visible to the authenticated user.
        """

        if getattr(self, "swagger_fake_view", False):  # pragma: no cover
            return Contract.objects.none()

        user = self.request.user
        queryset = Contract.objects.select_related(
            "organisation",
            "agent__user",
            "initiated_by__user",
            "legal_review",
            "signing",
        ).prefetch_related(
            "clauses__template",
            "revisions__clauses_changed",
            Prefetch(
                "versions",
                queryset=ContractVersion.objects.order_by("number"),
            ),
            Prefetch(
                "comments",
                queryset=ContractComment.objects.select_related(
                    "author", "clause", "version"
                ),
            ),
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
            # Returning ``none()`` prevents leaking contracts to unrelated users.
            return Contract.objects.none()

        return queryset.filter(filters).distinct()

    def get_serializer_class(self):
        """Pick the serializer matching the current viewset action.

        Returns:
            Type[Serializer]: Serializer class used for serialization.
        """

        if self.action == "create":
            return ContractCreateSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        """Return the list of contracts visible to the user.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized list of contracts.
        """

        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Return a single contract resource.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized contract representation.
        """

        contract = self.get_object()
        serializer = self.get_serializer(contract)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new contract and seed mandatory clauses.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized contract after creation.
        """

        serializer = ContractCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        # Version ``1`` captures the automatically generated clause baseline.
        contract.bump_version(created_by=request.user, notes="Initial version")
        contract.refresh_from_db()
        output = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="options")
    def options(self, request, *args, **kwargs):
        """Return helper metadata used by the proof-of-concept UI.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Metadata required by the front-end form.
        """

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
            # ``seen`` avoids duplicates when a user is a collaborator multiple
            # times with different roles.
            organisations.append(
                {"id": str(organisation.id), "name": organisation.name}
            )
            seen.add(organisation.id)

        agents = [
            {"id": str(agent.id), "display_name": agent.display_name}
            for agent in AgentProfile.objects.all().order_by("display_name")
        ]

        statuses = [
            {"value": value, "label": label} for value, label in Contract.Status.choices
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
        """Create a new clause attached to the contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized clause on success or an error response.
        """

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
        """Update an existing clause.

        Args:
            request: Incoming HTTP request.
            clause_id: Identifier of the clause to update.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized clause or an error payload.
        """

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
        """Remove a non-mandatory clause from the contract.

        Args:
            request: Incoming HTTP request.
            clause_id: Identifier of the clause to delete.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Empty payload with the appropriate HTTP status.
        """

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
        """Create a revision entry for the contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized revision payload.
        """

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
        """Return all revisions associated with the contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized revision list.
        """

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
        """Mark a revision as accepted and bump the contract version.

        Args:
            request: Incoming HTTP request.
            revision_id: Identifier of the revision to accept.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized revision after acceptance.
        """

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
        """Record the user's agreement on the contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Updated contract payload or an error message.
        """

        contract = self.get_object()
        if not self._user_is_owner(request.user, contract.organisation_id):
            detail = "Only organisation owners can update contract status."
            return error_response(
                detail,
                status.HTTP_403_FORBIDDEN,
                code="contract_status_owner_required",
                organisation_id=str(contract.organisation_id),
            )

        requirement = COLLABORATOR_FEATURES["contract_management"]
        if not collaborator_meets_requirement(request.user, requirement):
            return Response(
                requirement_denied_payload(
                    requirement,
                    "Upgrade required to access the contract workspace.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        contract.record_agreement(owner=is_owner, agent=is_agent)

        contract.refresh_from_db()
        serializer = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="legal/review")
    def create_legal_review(self, request, *args, **kwargs):
        """Start the legal review phase for a contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized legal review entry.
        """

        contract = self.get_object()

        if not self._is_owner(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        if not contract.has_full_agreement():
            return Response(
                {"detail": "Both parties must agree before legal review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            return error_response(
                detail,
                status.HTTP_400_BAD_REQUEST,
                code="contract_status_invalid_transition",
                current_status=contract.status,
                attempted_status=new_status,
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
        """Mark the legal review as complete and progress to signing.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized legal review entry.
        """

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
        review.verification_notes = serializer.validated_data.get(
            "verification_notes", ""
        )
        review.save(
            update_fields=[
                "verified_by",
                "verified_at",
                "verification_notes",
                "updated_at",
            ]
        )

        contract.status = Contract.Status.SIGNING
        contract.save(update_fields=["status", "updated_at"])

        output = ContractLegalReviewSerializer(review)
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="signing/init")
    def init_signing(self, request, *args, **kwargs):
        """Create or update the signing envelope information.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized signing payload.
        """

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
        """Return signing status for a contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized signing details.
        """

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
        """Process a webhook coming from the e-signature provider.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized signing payload after updates or an error.
        """

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

        signing.save(
            update_fields=["status", "last_payload", "completed_at", "updated_at"]
        )

        if signing.status == ContractSigning.Status.COMPLETED:
            contract.status = Contract.Status.ACTIVE
            contract.save(update_fields=["status", "updated_at"])
        elif signing.status == ContractSigning.Status.DECLINED:
            contract.status = Contract.Status.NEGOTIATION
            # Falling back to negotiation gives collaborators room to amend
            # clauses before re-initiating a new signing envelope.
            contract.save(update_fields=["status", "updated_at"])

        return Response(ContractSigningSerializer(signing).data)

    @action(detail=True, methods=["post"], url_path="expire")
    def expire(self, request, *args, **kwargs):
        """Force a contract into the expired state.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized contract payload after the change.
        """

        contract = self.get_object()

        if not (request.user.is_staff or request.user.is_superuser):
            return Response(status=status.HTTP_403_FORBIDDEN)

        contract.status = Contract.Status.EXPIRED
        contract.save(update_fields=["status", "updated_at"])

        serializer = ContractSerializer(contract, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="versions")
    def list_versions(self, request, *args, **kwargs):
        """Return the version history of a contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized version list.
        """

        contract = self.get_object()

        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        versions = contract.versions.all().order_by("number")
        serializer = ContractVersionSerializer(versions, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="versions/(?P<version_id>[^/.]+)/comments",
    )
    def version_comments(self, request, version_id=None, *args, **kwargs):
        """List or create comments for a specific contract version.

        Args:
            request: Incoming HTTP request.
            version_id: Identifier of the version whose comments are targeted.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized comments or creation output.
        """

        contract = self.get_object()
        if not self._user_is_owner(request.user, contract.organisation_id):
            detail = "Only organisation owners can modify clauses."
            return error_response(
                detail,
                status.HTTP_403_FORBIDDEN,
                code="contract_clause_owner_required",
                organisation_id=str(contract.organisation_id),
            )

        requirement = COLLABORATOR_FEATURES["contract_management"]
        if not collaborator_meets_requirement(request.user, requirement):
            return Response(
                requirement_denied_payload(
                    requirement,
                    "Upgrade required to access the contract workspace.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        if not self._user_can_view(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        template = ClauseTemplate.objects.filter(id=template_id).first()
        if not template:
            detail = "Clause template not found."
            return error_response(
                detail,
                status.HTTP_404_NOT_FOUND,
                code="contract_clause_template_not_found",
                template_id=str(template_id),
            )

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
        """Apply a status transition after validating permissions.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized contract payload after the transition.
        """

        contract = self.get_object()
        if not self._is_owner(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContractStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        if not self._is_valid_transition(contract.status, new_status):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if (
            new_status == Contract.Status.AGREEMENT
            and not contract.has_full_agreement()
        ):
            return Response(
                {
                    "detail": (
                        "Les deux parties doivent enregistrer leur accord avant de "
                        "passer le contrat en agreement."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        contract.status = new_status
        contract.save(update_fields=["status", "updated_at"])
        output = ContractSerializer(contract)
        return Response(output.data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_pdf(self, request, *args, **kwargs):
        """Return the signed PDF file associated with the contract.

        Args:
            request: Incoming HTTP request.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            FileResponse: Response streaming the PDF file.
        """

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
            pdf_file,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )

    def _is_owner(self, user, organisation_id):
        """Return whether the user owns the given organisation.

        Args:
            user: Authenticated user to inspect.
            organisation_id: Organisation identifier to match.

        Returns:
            bool: ``True`` if the user is an owner, ``False`` otherwise.
        """

        return Collaborator.objects.filter(
            user=user,
            organisation_id=organisation_id,
            role=Collaborator.Role.OWNER,
        ).exists()

    def _is_collaborator(self, user, organisation_id):
        """Return whether the user collaborates with the organisation.

        Args:
            user: Authenticated user to inspect.
            organisation_id: Organisation identifier to match.

        Returns:
            bool: ``True`` if the user collaborates, ``False`` otherwise.
        """

        return Collaborator.objects.filter(
            user=user, organisation_id=organisation_id
        ).exists()

    def _user_can_view(self, user, contract):
        """Determine whether the user can access the contract details.

        Args:
            user: Authenticated user to inspect.
            contract: Contract record being accessed.

        Returns:
            bool: ``True`` if the user has viewing rights.
        """

        if user.is_staff or user.is_superuser:
            return True
        if self._is_collaborator(user, contract.organisation_id):
            return True
        agent_profile = getattr(user, "agent_profile", None)
        return bool(agent_profile and agent_profile == contract.agent)

    def _can_edit_clauses(self, user, contract):
        """Return whether the user can create or update clauses.

        Args:
            user: Authenticated user to inspect.
            contract: Contract subject to editing.

        Returns:
            bool: ``True`` when the user can edit clauses.
        """

        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return False
        return self._is_collaborator(user, contract.organisation_id)

    def _can_propose_revision(self, user, contract):
        """Return whether the user can propose a contract revision.

        Args:
            user: Authenticated user to inspect.
            contract: Contract subject to the revision.

        Returns:
            bool: ``True`` when the user may create a revision.
        """

        if self._is_collaborator(user, contract.organisation_id):
            return True
        agent_profile = getattr(user, "agent_profile", None)
        return bool(agent_profile and agent_profile == contract.agent)

    def _get_clause(self, contract, clause_id):
        """Fetch a clause within a contract or raise ``Http404``.

        Args:
            contract: Contract housing the clause.
            clause_id: Identifier of the clause to retrieve.

        Returns:
            ContractClause: Clause instance when found.

        Raises:
            Http404: If the clause cannot be located.
        """

        try:
            return contract.clauses.get(id=clause_id)
        except ContractClause.DoesNotExist as exc:
            raise Http404 from exc

    def _get_version(self, contract, version_id):
        """Fetch a contract version or raise ``Http404``.

        Args:
            contract: Contract housing the version.
            version_id: Identifier of the version to fetch.

        Returns:
            ContractVersion: Version instance when found.

        Raises:
            Http404: If the version cannot be located.
        """

        try:
            return contract.versions.get(id=version_id)
        except ContractVersion.DoesNotExist as exc:
            raise Http404 from exc

    def _is_valid_transition(self, current_status, new_status):
        """Validate status transitions for the contract lifecycle.

        Args:
            current_status: The contract's current status value.
            new_status: Desired status value.

        Returns:
            bool: ``True`` when the transition is authorised.
        """

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
