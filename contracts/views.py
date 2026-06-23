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
from payments.models import PlatformFee
from users.models import AgentProfile

from .models import (
    ClauseTemplate,
    Contract,
    ContractAuditLog,
    ContractClause,
    ContractComment,
    ContractFile,
    ContractLegalReview,
    ContractRevision,
    ContractSigning,
    ContractVersion,
    RepresentationMandate,
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
    PlaceholderValueSerializer,
)
from .services import get_client_ip, log_contract_action


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
            "platform_fee",
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

        # Audit log: contract creation
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.CONTRACT_CREATED,
            actor=request.user,
            action_details={
                "organisation_id": str(contract.organisation_id),
                "agent_id": str(contract.agent_id),
                "title": contract.title,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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
            {"id": str(agent.id), "name": agent.name}
            for agent in AgentProfile.objects.all()
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__email")
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

        # Audit log: clause added
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_ADDED,
            actor=request.user,
            action_details={
                "clause_id": str(clause.id),
                "clause_title": clause.title,
                "is_mandatory": clause.is_mandatory,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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

        # Store old content for audit trail
        old_title = clause.title
        old_content = clause.content

        serializer = ContractClauseUpdateSerializer(
            instance=clause, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        clause = serializer.save()

        # Audit log: clause modified
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_MODIFIED,
            actor=request.user,
            action_details={
                "clause_id": str(clause.id),
                "clause_title": clause.title,
                "old_title": old_title,
                "old_content": old_content,
                "new_title": clause.title,
                "new_content": clause.content,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        output = ContractClauseSerializer(clause)
        return Response(output.data)

    @action(
        detail=True,
        methods=["patch"],
        url_path="clauses/(?P<clause_id>[^/.]+)/placeholders",
    )
    def update_placeholders(self, request, clause_id=None, *args, **kwargs):
        """Update placeholder values for a specific clause.

        Phase 2: Allows both owner and agent to fill in placeholder values
        during contract negotiation. Locked placeholders cannot be modified.
        Any placeholder update automatically revokes existing agreements to
        ensure parties re-agree to the updated terms.

        Args:
            request: Incoming HTTP request with placeholder_values JSON.
            clause_id: Identifier of the clause whose placeholders to update.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized clause with updated placeholders or error.
        """

        contract = self.get_object()
        clause = self._get_clause(contract, clause_id)

        # Both owner and agent can update placeholders during negotiation
        if not self._can_edit_clauses(request.user, contract):
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Store old values for audit trail
        old_placeholder_values = (
            clause.placeholder_values.copy() if clause.placeholder_values else {}
        )

        serializer = PlaceholderValueSerializer(
            instance=clause,
            data=request.data,
            partial=True,
            context={"clause": clause},
        )
        serializer.is_valid(raise_exception=True)
        clause = serializer.save()

        # Audit log: placeholder values updated
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_MODIFIED,
            actor=request.user,
            action_details={
                "clause_id": str(clause.id),
                "clause_title": clause.title,
                "field_changed": "placeholder_values",
                "old_values": old_placeholder_values,
                "new_values": clause.placeholder_values,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        output = ContractClauseSerializer(clause)
        return Response(output.data)

    @update_clause.mapping.delete
    def delete_clause(self, request, clause_id=None, *args, **kwargs):
        """Remove a non-mandatory clause from the contract.

        When a clause is deleted, any existing owner/agent agreements are
        automatically revoked. This ensures both parties must re-agree to
        the updated contract terms before proceeding to signature.

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

        # CRITICAL: Revoke any existing agreements when a clause is deleted
        # Both parties must re-agree to the updated contract terms
        had_owner_agreement = contract.owner_agreed_at is not None
        had_agent_agreement = contract.agent_agreed_at is not None

        if had_owner_agreement or had_agent_agreement:
            contract.owner_agreed_at = None
            contract.agent_agreed_at = None
            contract.save(
                update_fields=["owner_agreed_at", "agent_agreed_at", "updated_at"]
            )

        # Store clause info before deletion for audit trail
        clause_title = clause.title
        clause_content = clause.content
        clause_id_str = str(clause.id)

        clause.delete()

        # Audit log: clause deleted
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_DELETED,
            actor=request.user,
            action_details={
                "clause_id": clause_id_str,
                "clause_title": clause_title,
                "clause_content": clause_content,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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

        # Audit log: revision created
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.REVISION_CREATED,
            actor=request.user,
            action_details={
                "revision_id": str(revision.id),
                "comment": revision.comment,
                "clause_ids": [str(cid) for cid in clause_ids],
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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

        # Audit log: revision accepted
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.REVISION_ACCEPTED,
            actor=request.user,
            action_details={
                "revision_id": str(revision.id),
                "proposed_by": revision.proposed_by.email,
                "comment": revision.comment,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        contract.refresh_from_db()
        serializer = ContractRevisionSerializer(revision)
        return Response(serializer.data)

    @accept_revision.mapping.delete
    def reject_revision(self, request, revision_id=None, *args, **kwargs):
        """Mark a revision as rejected without bumping the contract version.

        When a revision is rejected, it remains in the revision history but
        cannot be accepted later. This provides a clear audit trail of
        rejected proposals during negotiation.

        Args:
            request: Incoming HTTP request.
            revision_id: Identifier of the revision to reject.
            *args: Positional arguments forwarded by DRF.
            **kwargs: Keyword arguments forwarded by DRF.

        Returns:
            Response: Serialized revision after rejection.
        """

        contract = self.get_object()
        if not self._is_collaborator(request.user, contract.organisation_id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            revision = contract.revisions.get(id=revision_id)
        except ContractRevision.DoesNotExist as exc:
            raise Http404 from exc

        # Cannot reject an already accepted or rejected revision
        if revision.accepted is not None:
            return Response(
                {"detail": "Revision has already been reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        revision.accepted = False
        revision.save(update_fields=["accepted", "updated_at"])

        # Audit log: revision rejected
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.REVISION_REJECTED,
            actor=request.user,
            action_details={
                "revision_id": str(revision.id),
                "proposed_by": revision.proposed_by.email,
                "comment": revision.comment,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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
            return Response(
                {
                    "detail": "Le contrat doit être en négociation pour valider l'accord."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        contract.record_agreement(owner=is_owner, agent=is_agent)

        # Audit log: agreement recorded
        if is_owner:
            log_contract_action(
                contract=contract,
                action=ContractAuditLog.Action.OWNER_AGREED,
                actor=request.user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        elif is_agent:
            log_contract_action(
                contract=contract,
                action=ContractAuditLog.Action.AGENT_AGREED,
                actor=request.user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

        contract.refresh_from_db()

        # Auto-transition to AGREEMENT and generate platform fee invoice when
        # both parties have recorded their consent.
        if (
            contract.has_full_agreement()
            and contract.status == Contract.Status.NEGOTIATION
        ):
            contract.status = Contract.Status.AGREEMENT
            contract.save(update_fields=["status", "updated_at"])
            contract.generate_platform_fee()
            log_contract_action(
                contract=contract,
                action=ContractAuditLog.Action.PLATFORM_FEE_GENERATED,
                actor=request.user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
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

        # Audit log: submitted for legal review
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.SUBMITTED_FOR_REVIEW,
            actor=request.user,
            action_details={
                "review_id": str(review.id),
                "notes": review.notes,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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

        # Audit log: legal review approved
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.LEGAL_APPROVED,
            actor=request.user,
            action_details={
                "review_id": str(review.id),
                "verification_notes": review.verification_notes,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        output = ContractLegalReviewSerializer(review)
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="signing/init")
    def init_signing(self, request, *args, **kwargs):
        """Create or update the signing envelope information.

        Phase 2: Before signature initiation, validates that both parties have
        valid representation mandates. This ensures legal authorization for
        contract execution.

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

        # Paywall: platform fee must be fully paid before DocuSign envelope creation.
        try:
            fee = contract.platform_fee
        except PlatformFee.DoesNotExist:
            fee = None

        if fee is None or fee.status != PlatformFee.Status.PAID:
            amount_str = str(fee.amount_due) if fee else "N/A"
            return Response(
                {
                    "detail": (
                        f"Platform fee of €{amount_str} must be settled to unlock "
                        "electronic signing and legal document access."
                    ),
                    "fee_status": fee.status if fee else None,
                    "amount_due": amount_str,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # Phase 2: Validate representation mandates before signature
        if not self._has_valid_mandate(contract):
            missing = self._get_missing_mandates(contract)
            return Response(
                {
                    "detail": "Valid representation mandate required for signing.",
                    "missing_mandates": missing,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        # Audit log: signature initiated
        log_contract_action(
            contract=contract,
            action=ContractAuditLog.Action.SIGNATURE_INITIATED,
            actor=request.user,
            action_details={
                "signing_id": str(signing.id),
                "envelope_id": signing.envelope_id,
            },
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
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

        # Generate (or refresh) the platform fee whenever the contract
        # transitions to AGREEMENT status — idempotent, safe to call twice.
        if new_status == Contract.Status.AGREEMENT:
            contract.generate_platform_fee()

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

        Both collaborators (organisation side) and agents (athlete side) can
        edit clauses during DRAFT and NEGOTIATION phases. This enables true
        bi-directional negotiation.

        Args:
            user: Authenticated user to inspect.
            contract: Contract subject to editing.

        Returns:
            bool: ``True`` when the user can edit clauses.
        """

        if contract.status not in {Contract.Status.DRAFT, Contract.Status.NEGOTIATION}:
            return False

        # Organisation collaborators can edit
        if self._is_collaborator(user, contract.organisation_id):
            return True

        # Agents representing the athlete can also edit
        agent_profile = getattr(user, "agent_profile", None)
        return bool(agent_profile and agent_profile == contract.agent)

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

    def _has_valid_mandate(self, contract):
        """Check if both parties have valid representation mandates.

        Phase 2: Validates that the agent has a verified mandate for the athlete
        and a collaborator has a verified mandate for the organisation.

        Args:
            contract: Contract instance to validate.

        Returns:
            bool: ``True`` if both mandates are valid, ``False`` otherwise.
        """

        today = timezone.now().date()

        # Check agent mandate - agent should have at least one verified mandate
        agent_mandate_exists = (
            RepresentationMandate.objects.filter(
                agent=contract.agent,
                verified=True,
                valid_from__lte=today,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
            .exists()
        )

        # Check collaborator mandate for organisation
        # Find the owner collaborator for this organisation
        owner_collaborator = Collaborator.objects.filter(
            organisation=contract.organisation,
            role=Collaborator.Role.OWNER,
        ).first()

        collaborator_mandate_exists = False
        if owner_collaborator:
            collaborator_mandate_exists = (
                RepresentationMandate.objects.filter(
                    collaborator=owner_collaborator,
                    organisation=contract.organisation,
                    verified=True,
                    valid_from__lte=today,
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
                .exists()
            )

        return agent_mandate_exists and collaborator_mandate_exists

    def _get_missing_mandates(self, contract):
        """Return a list of missing or invalid mandates.

        Phase 2: Provides detailed feedback about which mandates are missing
        to help users complete the requirements for signature.

        Args:
            contract: Contract instance to check.

        Returns:
            list: List of missing mandate descriptions.
        """

        today = timezone.now().date()
        missing = []

        # Check agent mandate
        agent_mandate_exists = (
            RepresentationMandate.objects.filter(
                agent=contract.agent,
                verified=True,
                valid_from__lte=today,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
            .exists()
        )

        if not agent_mandate_exists:
            missing.append(
                {
                    "party": "agent",
                    "agent_id": str(contract.agent.id),
                    "reason": "No valid verified mandate found for agent",
                }
            )

        # Check collaborator mandate
        owner_collaborator = Collaborator.objects.filter(
            organisation=contract.organisation,
            role=Collaborator.Role.OWNER,
        ).first()

        if owner_collaborator:
            collaborator_mandate_exists = (
                RepresentationMandate.objects.filter(
                    collaborator=owner_collaborator,
                    organisation=contract.organisation,
                    verified=True,
                    valid_from__lte=today,
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
                .exists()
            )

            if not collaborator_mandate_exists:
                missing.append(
                    {
                        "party": "organisation",
                        "organisation_id": str(contract.organisation_id),
                        "reason": "No valid verified mandate found for organisation owner",
                    }
                )
        else:
            missing.append(
                {
                    "party": "organisation",
                    "organisation_id": str(contract.organisation_id),
                    "reason": "No owner collaborator found for organisation",
                }
            )

        return missing

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
