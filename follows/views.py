"""API views for creating, removing, and listing follow relationships."""

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from athletes.models import Athlete
from organisations.models import Collaborator

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import (
    get_collaborator_plan_features,
    requirement_denied_payload,
    user_feature_requirement,
)
from core.responses import error_response
from .models import Follow
from .permissions import IsCollaboratorUser
from .serializers import FollowSerializer


class AthleteFollowView(APIView):
    """Create or remove follow relationships for the authenticated user.

    The view orchestrates collaborator lookup, subscription entitlement
    validation, and creation/deletion of :class:`follows.models.Follow`
    records. Keeping this logic centralised ensures the same guardrails apply
    whether requests originate from the dashboard or future integrations.
    """

    permission_classes = (permissions.IsAuthenticated, IsCollaboratorUser)

    def _get_collaborator(self, request):
        """Return the collaborator referenced in the request data.

        Args:
            request: Incoming request whose body or query parameters may
                include a ``collaborator_id`` value.

        Returns:
            organisations.models.Collaborator: Collaborator tied to the
            authenticated user.

        Raises:
            Collaborator.DoesNotExist: Raised when the user is not linked to a
            collaborator and no collaborator can be derived automatically.
        """

        collaborator_id = request.data.get(
            "collaborator_id"
        ) or request.query_params.get("collaborator_id")
        queryset = Collaborator.objects.filter(user=request.user)
        if collaborator_id:
            return get_object_or_404(queryset, id=collaborator_id)

        collaborator = queryset.first()
        if collaborator is None:
            raise Collaborator.DoesNotExist
        return collaborator

    def _enforce_follow_limits(self, request, collaborator):
        """Verify subscription limits before allowing a follow to be created.

        Args:
            request: Incoming API request used to resolve feature requirements.
            collaborator: Collaborator attempting to follow an athlete.

        Returns:
            Optional[Response]: ``None`` when the request may proceed or an
            HTTP 403 response describing the restriction.
        """

        features = get_collaborator_plan_features(
            request.user,
            collaborator.organisation,
        )
        max_follows = features.get("max_follows")
        try:
            max_follows = int(max_follows)
        except (TypeError, ValueError):
            max_follows = 0

        requirement, granted = user_feature_requirement(request.user, "follow_slots")
        requirement = requirement or COLLABORATOR_FEATURES["follow_slots"]
        if not granted and max_follows <= 0:
            payload = requirement_denied_payload(
                requirement,
                "Follow limit reached. Upgrade your organisation plan to track more athletes.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        if max_follows > 0:
            # Count follows for the entire organisation because slots are
            # shared across collaborators.
            current_count = Follow.objects.filter(
                collaborator__organisation=collaborator.organisation,
            ).count()
            if current_count >= max_follows:
                payload = requirement_denied_payload(
                    requirement,
                    "Follow limit reached. Upgrade your organisation plan to track more athletes.",
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)

        return None

    def post(self, request, athlete_id):
        """Create a follow relationship when the collaborator has capacity.

        Args:
            request: HTTP request initiating the follow action.
            athlete_id: Primary key of the athlete being followed.

        Returns:
            Response: 201 Created when a new follow is made, 200 OK when an
            existing follow is re-used, 400 Bad Request when the user lacks a
            collaborator, or 403 Forbidden when subscription limits are hit.
        """

        try:
            collaborator = self._get_collaborator(request)
        except Collaborator.DoesNotExist:
            return error_response(
                "Collaborator membership required.",
                status.HTTP_400_BAD_REQUEST,
                code="collaborator_membership_required",
            )

        denial = self._enforce_follow_limits(request, collaborator)
        if denial is not None:
            return denial

        athlete = get_object_or_404(Athlete, id=athlete_id)
        # ``get_or_create`` avoids duplicate records when the client retries a
        # request or when concurrent requests target the same athlete.
        follow, created = Follow.objects.get_or_create(
            collaborator=collaborator,
            athlete=athlete,
        )
        serializer = FollowSerializer(follow)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=response_status)

    def delete(self, request, athlete_id):
        """Remove a follow relationship owned by the collaborator.

        Args:
            request: HTTP request initiating the unfollow action.
            athlete_id: Primary key of the athlete to stop tracking.

        Returns:
            Response: 204 No Content when a relationship is removed, 400 Bad
            Request when the user lacks a collaborator, or 404 Not Found when
            no follow existed.
        """

        try:
            collaborator = self._get_collaborator(request)
        except Collaborator.DoesNotExist:
            return error_response(
                "Collaborator membership required.",
                status.HTTP_400_BAD_REQUEST,
                code="collaborator_membership_required",
            )

        athlete = get_object_or_404(Athlete, id=athlete_id)
        deleted_count, _ = Follow.objects.filter(
            collaborator=collaborator,
            athlete=athlete,
        ).delete()
        if deleted_count:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return error_response(
            "Follow relationship not found.",
            status.HTTP_404_NOT_FOUND,
            code="follow_relationship_not_found",
        )


class MyFollowsView(APIView):
    """List all athletes followed by the authenticated collaborator.

    The endpoint collects follows across every collaborator membership tied to
    the current user. This mirrors how the dashboard aggregates data and keeps
    the public API consistent with the product experience.
    """

    permission_classes = (permissions.IsAuthenticated, IsCollaboratorUser)

    def get(self, request, *_args, **_kwargs):
        """Return serialized follow records for the requesting user.

        Args:
            request: HTTP request initiating the fetch.
            *_args: Positional arguments provided by Django (unused).
            **_kwargs: Keyword arguments provided by Django (unused).

        Returns:
            Response: 200 OK response containing serialized follow data.
        """

        collaborator_ids = Collaborator.objects.filter(user=request.user).values_list(
            "id", flat=True
        )
        # Selecting related sport data avoids N+1 queries when rendering the
        # athlete serializer.
        follows = Follow.objects.filter(
            collaborator_id__in=collaborator_ids
        ).select_related("athlete__sport")
        serializer = FollowSerializer(follows, many=True)
        return Response(serializer.data)
