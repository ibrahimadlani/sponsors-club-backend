"""REST API views for messaging threads and messages."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Message, Thread
from .permissions import IsThreadParticipant
from .serializers import MessageSerializer, ThreadSerializer


class ThreadPagination(PageNumberPagination):
    """Pagination settings for thread listings."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ThreadMessagesPagination(PageNumberPagination):
    """Pagination configuration for thread message listings."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ThreadListView(APIView):
    """List the messaging threads for the authenticated user."""

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ThreadPagination

    def get_queryset(self):
        """Return threads where the requester participates."""

        user = self.request.user
        last_message_prefetch = Prefetch(
            "messages",
            queryset=Message.objects.select_related("sender").order_by("-created_at")[:1],
            to_attr="last_message_list",
        )
        return (
            Thread.objects.select_related(
                "collaborator__user",
                "collaborator__organisation",
                "agent__user",
                "athlete",
            )
            .prefetch_related(last_message_prefetch)
            .filter(Q(collaborator__user=user) | Q(agent__user=user))
            .order_by("-last_message_at", "-created_at")
        )

    def get(self, request, *args: Any, **kwargs: Any) -> Response:
        """Return a paginated list of threads."""

        del args, kwargs
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ThreadSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class ThreadMessagesView(APIView):
    """List existing messages or create a new message within a thread."""

    permission_classes = (permissions.IsAuthenticated, IsThreadParticipant)
    pagination_class = ThreadMessagesPagination

    def _get_thread(self, request, thread_id):
        thread = get_object_or_404(
            Thread.objects.select_related(
                "collaborator__user",
                "agent__user",
            ),
            id=thread_id,
        )
        self.check_object_permissions(request, thread)
        return thread

    def get(self, request, thread_id, *args: Any, **kwargs: Any) -> Response:
        """Return paginated messages for the requested thread."""

        del args, kwargs
        thread = self._get_thread(request, thread_id)
        queryset = (
            Message.objects.filter(thread=thread)
            .select_related("sender")
            .order_by("created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = MessageSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, thread_id, *args: Any, **kwargs: Any) -> Response:
        """Create a new message within the thread."""

        del args, kwargs
        thread = self._get_thread(request, thread_id)
        serializer = MessageSerializer(
            data=request.data,
            context={"request": request, "thread": thread},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        output = MessageSerializer(message, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class MessageReadView(APIView):
    """Mark a message as read."""

    permission_classes = (permissions.IsAuthenticated, IsThreadParticipant)

    def post(self, request, message_id, *args: Any, **kwargs: Any) -> Response:
        """Mark the specified message as read for the current user."""

        del args, kwargs
        message = get_object_or_404(
            Message.objects.select_related(
                "thread__collaborator__user",
                "thread__agent__user",
            ),
            id=message_id,
        )
        self.check_object_permissions(request, message)

        if not message.is_read:
            message.is_read = True
            message.save(update_fields=["is_read", "updated_at"])

        serializer = MessageSerializer(message, context={"request": request})
        return Response(serializer.data)
