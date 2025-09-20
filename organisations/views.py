"""View layer for organisation endpoints."""

from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
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
    IsCollaboratorAccount,
    IsOrganisationOwner,
)
from .serializers import (
    CollaboratorCreateSerializer,
    CollaboratorSerializer,
    OrganisationCreateSerializer,
    OrganisationListFilter,
    OrganisationSerializer,
)


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
    filterset_fields = ("sector", "size", "country")

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
            "create": self._organisation_account_permissions,
            "list": self._organisation_account_permissions,
            "update": self._owner_permissions,
            "partial_update": self._owner_permissions,
            "collaborators": self._collaborator_permissions,
            "add_collaborator": self._collaborator_permissions,
            "remove_collaborator": lambda: [permissions.IsAuthenticated()],
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

    def _organisation_account_permissions(self):
        """Return permissions for list operations restricted to collaborator accounts."""
        return [permissions.IsAuthenticated(), IsCollaboratorAccount()]
