"""View layer for organisation endpoints."""

from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import (
    collaborator_meets_requirement,
    get_collaborator_plan_features,
    requirement_denied_payload,
)
from .models import Collaborator, Organisation
from .permissions import (
    IsAuthenticatedCollaborator,
    IsOrganisationCreator,
    IsOrganisationOwner,
)
from .serializers import (
    CollaboratorCreateSerializer,
    CollaboratorJobTitleSerializer,
    CollaboratorSerializer,
    OrganisationCreateSerializer,
    OrganisationInviteCreateSerializer,
    OrganisationInviteSerializer,
    OrganisationJoinSerializer,
    OrganisationListFilter,
    OrganisationSerializer,
    OwnershipTransferSerializer,
)
from .throttling import InviteCreateThrottle, InviteJoinThrottle


class OrganisationViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
):
    """Expose CRUD operations and collaborator management for organisations."""

    organisation = None
    queryset = Organisation.objects.all().order_by("name")
    serializer_class = OrganisationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("type", "industry", "address_country")

    def get_serializer_class(self):
        if self.action == "create":
            return OrganisationCreateSerializer
        return OrganisationSerializer

    def perform_create(self, serializer):
        """Persist a newly created organisation instance."""
        serializer.save()

    def get_permissions(self):
        """Return action-specific permission instances."""
        action_permissions = {
            "create": self._organisation_create_permissions,
            "list": self._staff_permissions,
            "retrieve": self._collaborator_permissions,
            "update": self._owner_permissions,
            "partial_update": self._owner_permissions,
            "collaborators": self._collaborator_permissions,
            "add_collaborator": self._collaborator_permissions,
            "remove_collaborator": lambda: [permissions.IsAuthenticated()],
            "invites": self._owner_permissions,
            "revoke_invite": self._owner_permissions,
            "transfer_ownership": self._owner_permissions,
            "update_job_title": lambda: [permissions.IsAuthenticated()],
        }
        resolver = action_permissions.get(self.action)
        if resolver is not None:
            return resolver()
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        """Return organisations filtered by optional query parameters."""
        filter_serializer = OrganisationListFilter(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)

        queryset = self.filter_queryset(self.get_queryset())
        filters = filter_serializer.validated_data
        if filters:
            queryset = queryset.filter(**filters)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="collaborators")
    def collaborators(self, _request, *_args, **_kwargs):
        """Return the collaborators associated with the organisation."""
        organisation = self._get_organisation()
        collaborators = organisation.collaborators.select_related("user").all()
        serializer = CollaboratorSerializer(collaborators, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="collaborators/add")
    def add_collaborator(self, request, *_args, **_kwargs):
        """Invite an existing user to collaborate with the organisation."""
        organisation = self._get_organisation()
        if not Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).exists():
            return Response(
                {"detail": "Only owners can add collaborators."},
                status=status.HTTP_403_FORBIDDEN,
            )

        requirement = COLLABORATOR_FEATURES["collaborator_invites"]
        if not collaborator_meets_requirement(request.user, requirement):
            payload = requirement_denied_payload(
                requirement,
                "Upgrade your organisation plan to invite additional collaborators.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        serializer = CollaboratorCreateSerializer(
            data=request.data,
            context={"organisation": organisation},
        )
        serializer.is_valid(raise_exception=True)

        features = get_collaborator_plan_features(request.user, organisation)
        max_collaborators = features.get("max_collaborators")
        try:
            max_collaborators = int(max_collaborators)
        except (TypeError, ValueError):
            max_collaborators = 0
        if max_collaborators > 0:
            current_count = organisation.collaborators.count()
            if current_count >= max_collaborators:
                requirement = COLLABORATOR_FEATURES["collaborator_slots"]
                payload = requirement_denied_payload(
                    requirement,
                    (
                        "Collaborator limit reached. Upgrade your organisation "
                        "plan to add more teammates."
                    ),
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)
        collaborator = serializer.save()
        return Response(
            CollaboratorSerializer(collaborator).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["delete"],
        url_path="collaborators/(?P<collaborator_id>[^/.]+)",
    )
    def remove_collaborator(self, request, collaborator_id=None):
        """Remove a collaborator if the requester is an organisation owner."""
        try:
            collaborator = Collaborator.objects.select_related("organisation").get(
                id=collaborator_id
            )
        except Collaborator.DoesNotExist:
            return Response(
                {"detail": "Collaborator not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if not Collaborator.objects.filter(
            organisation=collaborator.organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).exists():
            return Response(
                {"detail": "Only owners can remove collaborators."},
                status=status.HTTP_403_FORBIDDEN,
            )

        requirement = COLLABORATOR_FEATURES["collaborator_invites"]
        if not collaborator_meets_requirement(request.user, requirement):
            payload = requirement_denied_payload(
                requirement,
                "Upgrade your organisation plan to manage collaborators.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        collaborator.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="invites")
    def invites(self, request, *_args, **_kwargs):
        """List or create invitation codes for the organisation."""

        # Apply throttling for POST requests (creation)
        if request.method.lower() == "post":
            throttle = InviteCreateThrottle()
            if not throttle.allow_request(request, self):
                self.throttled(request, throttle.wait())

        organisation = self._get_organisation()
        owner_collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).first()

        if request.method.lower() == "post":
            if owner_collaborator is None and not request.user.is_staff:
                return Response(
                    {"detail": "Only owners can create invitation codes."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if owner_collaborator is None:
                owner_collaborator = organisation.collaborators.filter(
                    role=Collaborator.Role.OWNER
                ).first()
            if owner_collaborator is None:
                return Response(
                    {"detail": "Organisation has no owner to attribute the invite."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = OrganisationInviteCreateSerializer(
                data=request.data,
                context={
                    "organisation": organisation,
                    "creator": owner_collaborator,
                },
            )
            serializer.is_valid(raise_exception=True)
            invite = serializer.save()

            from .models import InvitationAuditLog
            from .services import log_invitation_action, send_invitation_created_email

            log_invitation_action(
                invite, InvitationAuditLog.Action.CREATED, request=request
            )
            if invite.target_email:
                send_invitation_created_email(invite, invite.target_email)

            return Response(
                OrganisationInviteSerializer(invite).data,
                status=status.HTTP_201_CREATED,
            )

        # Handle filtering by status
        status_filter = request.query_params.get("status", None)
        invites = organisation.invites.all()

        if status_filter == "active":
            invites = invites.active()
        elif status_filter == "expired":
            invites = invites.expired()
        elif status_filter == "used":
            invites = invites.used()

        invites = invites.order_by("-created_at")
        serializer = OrganisationInviteSerializer(invites, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["delete"],
        url_path="invites/(?P<invite_id>[^/.]+)",
    )
    def revoke_invite(self, request, pk=None, invite_id=None):
        """Revoke/delete an invitation code."""
        organisation = self._get_organisation()

        # Check if user is owner
        if not Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).exists():
            return Response(
                {"detail": "Only organisation owners can revoke invitations."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Fetch the invite
        try:
            from .models import OrganisationInvite

            invite = OrganisationInvite.objects.get(
                id=invite_id,
                organisation=organisation,
            )
        except OrganisationInvite.DoesNotExist:
            return Response(
                {"detail": "Invitation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Optionally prevent deletion of already used invites
        if invite.is_used:
            return Response(
                {"detail": "Cannot revoke an invitation that has already been used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import InvitationAuditLog
        from .services import log_invitation_action

        log_invitation_action(
            invite, InvitationAuditLog.Action.REVOKED, request=request
        )
        invite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["patch"],
        url_path="collaborators/(?P<collaborator_id>[^/.]+)/job-title",
    )
    def update_job_title(self, request, collaborator_id=None, *_args, **_kwargs):
        """Allow owners or the collaborator themselves to edit the job title."""

        organisation = self._get_organisation()
        try:
            collaborator = organisation.collaborators.select_related("user").get(
                id=collaborator_id
            )
        except Collaborator.DoesNotExist:
            return Response(
                {"detail": "Collaborator not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_owner = Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).exists()
        is_self = collaborator.user_id == request.user.id
        if not (is_owner or is_self or request.user.is_staff):
            return Response(
                {"detail": "You do not have permission to update this collaborator."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaboratorJobTitleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collaborator.job_title = serializer.validated_data["job_title"]
        collaborator.save(update_fields=["job_title", "updated_at"])
        return Response(CollaboratorSerializer(collaborator).data)

    @action(detail=True, methods=["post"], url_path="transfer-ownership")
    def transfer_ownership(self, request, *_args, **_kwargs):
        """Transfer organisation ownership to another collaborator."""

        organisation = self._get_organisation()
        serializer = OwnershipTransferSerializer(
            data=request.data,
            context={"organisation": organisation},
        )
        serializer.is_valid(raise_exception=True)

        new_owner: Collaborator = serializer.validated_data["collaborator"]
        try:
            current_owner = organisation.collaborators.get(role=Collaborator.Role.OWNER)
        except Collaborator.DoesNotExist:
            current_owner = None

        if current_owner and current_owner.id == new_owner.id:
            return Response(
                {"detail": "Collaborator is already the owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_owner:
            current_owner.role = Collaborator.Role.MEMBER
            current_owner.save(update_fields=["role", "updated_at"])

        new_owner.role = Collaborator.Role.OWNER
        new_owner.save(update_fields=["role", "updated_at"])
        # Persist owner as collaborator object
        organisation.owner = new_owner
        organisation.save(update_fields=["owner", "updated_at"])

        return Response(CollaboratorSerializer(new_owner).data)

    def _get_organisation(self):
        """Fetch and cache the organisation associated with the current action."""
        if getattr(self, "organisation", None) is not None:
            return self.organisation

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)
        queryset = self.filter_queryset(self.get_queryset())
        self.organisation = generics.get_object_or_404(
            queryset,
            **{self.lookup_field: lookup_value},
        )
        return self.organisation

    def _owner_permissions(self):
        """Return permissions that restrict access to organisation owners."""
        self._get_organisation()
        return [permissions.IsAuthenticated(), IsOrganisationOwner()]

    def _collaborator_permissions(self):
        """Return permissions that restrict access to organisation collaborators."""
        self._get_organisation()
        return [permissions.IsAuthenticated(), IsAuthenticatedCollaborator()]

    def _organisation_create_permissions(self):
        """Return permissions for create operations restricted to eligible users."""
        return [permissions.IsAuthenticated(), IsOrganisationCreator()]

    def _staff_permissions(self):
        """Return permissions restricted to staff members."""
        return [permissions.IsAdminUser()]


class OrganisationJoinView(APIView):
    """Allow collaborators to join an organisation using an invitation code."""

    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (InviteJoinThrottle,)

    def post(self, request, *_args, **_kwargs):
        serializer = OrganisationJoinSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        collaborator = serializer.save()
        return Response(
            CollaboratorSerializer(collaborator).data,
            status=status.HTTP_201_CREATED,
        )
