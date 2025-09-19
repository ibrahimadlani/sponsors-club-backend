"""Views providing messaging thread and message APIs."""

# pylint: disable=no-member

from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from core.feature_matrix import AGENT_FEATURES
from core.permissions import (
    agent_meets_requirement,
    get_agent_profile,
    requirement_denied_payload,
)
from .models import Message, Thread
from .permissions import IsThreadParticipant
from .serializers import (
    MessageCreateSerializer,
    MessageReadSerializer,
    MessageSerializer,
    ThreadCreateSerializer,
    ThreadSerializer,
)


MESSAGING_INITIATE_REQUIREMENT = AGENT_FEATURES["messaging_initiate"]


class ThreadPagination(PageNumberPagination):
    """Pagination configuration for thread listings."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ThreadViewSet(viewsets.GenericViewSet):
    """List and create messaging threads."""

    serializer_class = ThreadSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ThreadPagination

    def get_queryset(self):
        """Return the threads visible to the requesting user."""

        user = self.request.user
        return (
            Thread.objects.select_related(
                "collaborator__organisation",
                "collaborator__user",
                "agent__user",
                "athlete__sport",
            )
            .filter(Q(collaborator__user=user) | Q(agent__user=user))
            .order_by("-last_message_at", "-created_at")
        )

    def list(self, request, *args, **kwargs):  # pylint: disable=unused-argument
        """Return a paginated list of threads for the current user."""

        del args, kwargs

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = ThreadSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):  # pylint: disable=unused-argument
        """Create a messaging thread after validating entitlement."""

        del args, kwargs

        serializer = ThreadCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        agent = validated["agent"]
        collaborator = validated["collaborator"]
        user = request.user

        agent_profile = get_agent_profile(user)
        if agent_profile and agent_profile.id == agent.id:
            if not agent_meets_requirement(user, MESSAGING_INITIATE_REQUIREMENT):
                payload = requirement_denied_payload(
                    MESSAGING_INITIATE_REQUIREMENT,
                    "Permission denied.",
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)
        elif collaborator.user_id != user.id and not request.user.is_staff:
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )
        thread = serializer.save()
        output = ThreadSerializer(thread)
        return Response(output.data, status=status.HTTP_201_CREATED)


class ThreadMessagesPagination(PageNumberPagination):
    """Pagination configuration for thread message listings."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ThreadMessagesView(APIView):
    """List and create messages within a thread."""

    permission_classes = (IsThreadParticipant,)
    pagination_class = ThreadMessagesPagination

    def get_thread(self, request, thread_id):
        """Return the requested thread if the user has access."""

        thread = (
            Thread.objects.select_related(
                "collaborator__user",
                "agent__user",
            )
            .filter(id=thread_id)
            .first()
        )
        if thread and IsThreadParticipant().has_object_permission(
            request, self, thread
        ):
            return thread
        return None

    def get(self, request, thread_id):
        """Paginate and return messages for the given thread."""

        thread = self.get_thread(request, thread_id)
        if not thread:
            return Response(
                {"detail": "Thread not found or access denied."},
                status=status.HTTP_404_NOT_FOUND,
            )

        messages = (
            Message.objects.filter(thread=thread)
            .select_related("sender")
            .order_by("created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(messages, request, view=self)
        serializer = MessageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, thread_id):
        """Create a new message within the specified thread."""

        thread = self.get_thread(request, thread_id)
        if not thread:
            return Response(
                {"detail": "Thread not found or access denied."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = MessageCreateSerializer(
            data=request.data,
            context={"request": request, "thread": thread},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )


class MessageReadView(APIView):
    """Toggle read state for a specific message."""

    permission_classes = (IsThreadParticipant,)

    def patch(self, request, message_id):
        """Update the message read status if the user participates in the thread."""

        message = (
            Message.objects.select_related(
                "thread__collaborator__user",
                "thread__agent__user",
            )
            .filter(id=message_id)
            .first()
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

        serializer = MessageReadSerializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MessageSerializer(message).data)
