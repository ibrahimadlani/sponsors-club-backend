"""Views for listing and updating notifications."""


from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    requirement_denied_payload,
    user_feature_requirement,
)
from .models import Notification
from .serializers import NotificationReadSerializer, NotificationSerializer


class NotificationPagination(PageNumberPagination):
    """Pagination defaults for notification listing."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationListView(generics.ListAPIView):
    """List notifications for the authenticated user when permitted."""

    serializer_class = NotificationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = NotificationPagination

    def list(self, request, *args, **kwargs):
        """Return notifications or a feature-requirement denial."""

        requirement, granted = user_feature_requirement(request.user, 'notification_center')
        if requirement is not None and not granted:
            payload = requirement_denied_payload(
                requirement,
                'Upgrade required to access notifications.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """Filter notifications for the requesting user with optional read flag."""

        queryset = Notification.objects.filter(user=self.request.user).order_by('-created_at')
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            lowered = is_read.lower()
            if lowered in {'true', '1'}:
                queryset = queryset.filter(is_read=True)
            elif lowered in {'false', '0'}:
                queryset = queryset.filter(is_read=False)
        return queryset


class NotificationReadView(APIView):
    """Allow toggling the read state of a specific notification."""

    permission_classes = (permissions.IsAuthenticated,)

    def patch(self, request, notification_id):
        """Mark the notification as read/unread when permitted."""

        requirement, granted = user_feature_requirement(request.user, 'notification_center')
        if requirement is not None and not granted:
            payload = requirement_denied_payload(
                requirement,
                'Upgrade required to access notifications.',
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = NotificationReadSerializer(notification, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(NotificationSerializer(notification).data)
