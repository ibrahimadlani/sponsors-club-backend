"""Views for interacting with follow relationships."""

# pylint: disable=no-member

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
from .models import Follow
from .permissions import IsCollaboratorUser
from .serializers import FollowSerializer


class AthleteFollowView(APIView):
    """Create or remove follow relationships for the current collaborator."""

    permission_classes = (permissions.IsAuthenticated, IsCollaboratorUser)

    def _get_collaborator(self, request):
        """Return the collaborator referenced in the request payload or query params."""

        collaborator_id = (
            request.data.get('collaborator_id')
            or request.query_params.get('collaborator_id')
        )
        queryset = Collaborator.objects.filter(user=request.user)
        if collaborator_id:
            return get_object_or_404(queryset, id=collaborator_id)

        collaborator = queryset.first()
        if collaborator is None:
            raise Collaborator.DoesNotExist
        return collaborator

    def _enforce_follow_limits(self, request, collaborator):
        """Verify follow entitlements and return a denial response when needed."""

        features = get_collaborator_plan_features(
            request.user,
            collaborator.organisation,
        )
        max_follows = features.get('max_follows')
        try:
            max_follows = int(max_follows)
        except (TypeError, ValueError):
            max_follows = 0

        requirement, granted = user_feature_requirement(request.user, 'follow_slots')
        requirement = requirement or COLLABORATOR_FEATURES['follow_slots']
        if not granted and max_follows <= 0:
            payload = requirement_denied_payload(
                requirement,
                'Follow limit reached. Upgrade your organisation plan to track more athletes.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        if max_follows > 0:
            current_count = Follow.objects.filter(
                collaborator__organisation=collaborator.organisation,
            ).count()
            if current_count >= max_follows:
                payload = requirement_denied_payload(
                    requirement,
                    'Follow limit reached. Upgrade your organisation plan to track more athletes.',
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)

        return None

    def post(self, request, athlete_id):
        """Create a follow relationship if the collaborator has available slots."""

        try:
            collaborator = self._get_collaborator(request)
        except Collaborator.DoesNotExist:
            return Response(
                {'detail': 'Collaborator membership required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        denial = self._enforce_follow_limits(request, collaborator)
        if denial is not None:
            return denial

        athlete = get_object_or_404(Athlete, id=athlete_id)
        follow, created = Follow.objects.get_or_create(
            collaborator=collaborator,
            athlete=athlete,
        )
        serializer = FollowSerializer(follow)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=response_status)

    def delete(self, request, athlete_id):
        """Remove a follow relationship for the collaborator."""

        try:
            collaborator = self._get_collaborator(request)
        except Collaborator.DoesNotExist:
            return Response(
                {'detail': 'Collaborator membership required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        athlete = get_object_or_404(Athlete, id=athlete_id)
        deleted_count, _ = Follow.objects.filter(
            collaborator=collaborator,
            athlete=athlete,
        ).delete()
        if deleted_count:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {'detail': 'Follow relationship not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )


class MyFollowsView(APIView):
    """List all athletes followed by the authenticated collaborator."""

    permission_classes = (permissions.IsAuthenticated, IsCollaboratorUser)

    def get(self, request, *_args, **_kwargs):
        """Return serialized follow records for the requesting user."""

        collaborator_ids = (
            Collaborator.objects.filter(user=request.user)
            .values_list('id', flat=True)
        )
        follows = (
            Follow.objects.filter(collaborator_id__in=collaborator_ids)
            .select_related('athlete__sport')
        )
        serializer = FollowSerializer(follows, many=True)
        return Response(serializer.data)
