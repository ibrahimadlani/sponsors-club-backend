"""Views for listing and updating notifications.

The views enforce feature-flag checks before exposing notifications so that we
respect plan limits for different organisations.
"""

from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    requirement_denied_payload,
    user_feature_requirement,
)
from core.responses import error_response
from .models import Notification
from .serializers import NotificationReadSerializer, NotificationSerializer


class NotificationPagination(PageNumberPagination):
    """Pagination defaults for notification listing.

    Attributes:
        page_size (int): Default number of notifications returned in a page.
        page_size_query_param (str): Query parameter allowing clients to adjust
            the page size.
        max_page_size (int): Upper bound to prevent expensive fetches.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class NotificationListView(generics.ListAPIView):
    """List notifications for the authenticated user when permitted.

    Attributes:
        serializer_class (type): Serializer used for notification output.
        permission_classes (tuple[type, ...]): Set of access guards that require
            authentication.
        pagination_class (type): Pagination settings shared across requests.
    """

    serializer_class = NotificationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = NotificationPagination

    def list(self, request, *args, **kwargs):
        """Return notifications or a feature-requirement denial.

        Args:
            request (rest_framework.request.Request): The incoming request.
            *args: Positional arguments forwarded to DRF's implementation.
            **kwargs: Keyword arguments forwarded to DRF's implementation.

        Returns:
            rest_framework.response.Response: Paginated notifications or a
            denial payload when the user's plan disables the feature.
        """

        requirement, granted = user_feature_requirement(
            request.user, "notification_center"
        )
        if requirement is not None and not granted:
            # Mirror the permission denial structure used elsewhere so the
            # client can consistently render upgrade prompts.
            payload = requirement_denied_payload(
                requirement,
                "Upgrade required to access notifications.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """Filter notifications for the requesting user.

        Returns:
            django.db.models.QuerySet: Notifications sorted newest-first and
            optionally filtered by the ``is_read`` query parameter.
        """

        queryset = Notification.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            lowered = is_read.lower()
            if lowered in {"true", "1"}:
                # Accept common truthy values to make the endpoint flexible for
                # different clients (web, mobile, etc.).
                queryset = queryset.filter(is_read=True)
            elif lowered in {"false", "0"}:
                queryset = queryset.filter(is_read=False)
        return queryset


class NotificationReadView(APIView):
    """Allow toggling the read state of a specific notification.

    Attributes:
        permission_classes (tuple[type, ...]): Permissions required for the
            endpoint, which currently only enforce authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def patch(self, request, notification_id):
        """Mark the notification as read/unread when permitted.

        Args:
            request (rest_framework.request.Request): The incoming request
                containing the ``is_read`` flag.
            notification_id (uuid.UUID): Identifier of the notification to
                update.

        Returns:
            rest_framework.response.Response: Updated notification payload or a
            denial/not-found response depending on the access outcome.
        """

        requirement, granted = user_feature_requirement(
            request.user, "notification_center"
        )
        if requirement is not None and not granted:
            # The denial format matches the list endpoint so clients can reuse
            # their upgrade handling logic.
            payload = requirement_denied_payload(
                requirement,
                "Upgrade required to access notifications.",
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        try:
            notification = Notification.objects.get(
                id=notification_id, user=request.user
            )
        except Notification.DoesNotExist:
            return error_response(
                "Notification not found.",
                status.HTTP_404_NOT_FOUND,
                code="notification_not_found",
            )

        serializer = NotificationReadSerializer(
            notification, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        # Persist the new read state and reuse the list serializer to keep the
        # response format consistent with the listing endpoint.
        serializer.save()
        return Response(NotificationSerializer(notification).data)
