"""REST API views for messaging threads and messages."""

from __future__ import annotations

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Message, Thread
from .permissions import IsThreadParticipant
from .serializers import MessageSerializer, ThreadSerializer


class ThreadListView(generics.ListAPIView):
    """Return the threads the authenticated user participates in."""

    serializer_class = ThreadSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):  # type: ignore[override]
        user = self.request.user
        message_prefetch = Prefetch(
            "messages",
            queryset=(
                Message.objects.select_related("sender")
                .order_by("-created_at")
                .only(
                    "id",
                    "thread_id",
                    "sender_id",
                    "content",
                    "attachment",
                    "is_read",
                    "created_at",
                    "updated_at",
                )
            ),
            to_attr="_last_message_list",
        )
        return (
            Thread.objects.select_related(
                "collaborator__user",
                "collaborator__organisation",
                "agent__user",
                "athlete",
            )
            .prefetch_related(message_prefetch)
            .filter(Q(collaborator__user=user) | Q(agent__user=user))
            .order_by("-last_message_at", "-created_at")
        )

    def get_serializer_context(self):  # type: ignore[override]
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class ThreadMessagesPagination(PageNumberPagination):
    """Pagination defaults for listing messages inside a thread."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ThreadMessagesView(APIView):
    """List and create messages within a specific thread."""

    permission_classes = (IsThreadParticipant,)
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    pagination_class = ThreadMessagesPagination

    def get_thread(self, request, thread_id: str) -> Thread:
        thread = get_object_or_404(
            Thread.objects.select_related(
                "collaborator__user",
                "agent__user",
                "athlete",
            ),
            id=thread_id,
        )
        self.check_object_permissions(request, thread)
        return thread

    def get(self, request, thread_id: str):
        thread = self.get_thread(request, thread_id)
        queryset = (
            Message.objects.filter(thread=thread)
            .select_related("sender")
            .order_by("created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = MessageSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, thread_id: str):
        thread = self.get_thread(request, thread_id)
        serializer = MessageSerializer(
            data=request.data,
            context={"request": request, "thread": thread},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        output = MessageSerializer(message, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class MessageReadView(APIView):
    """Mark a specific message as read for the current user."""

    permission_classes = (IsThreadParticipant,)

    def post(self, request, message_id: str):
        message = get_object_or_404(
            Message.objects.select_related(
                "thread__collaborator__user",
                "thread__agent__user",
            ),
            id=message_id,
        )
        if not message:
            return Response(
                {"detail": "Message not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not IsThreadParticipant().has_object_permission(request, self, message):
            return Response(
                {"detail": "Access denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if message.sender_id == request.user.id:
            return Response(
                {"detail": "Only the message recipient may update read status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MessageReadSerializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MessageSerializer(message).data)
      