"""Views providing messaging thread and message APIs.

The module focuses on the presentation layer of the messaging feature. It
contains viewsets and API views that orchestrate authentication checks,
pagination concerns, and serializer interactions for threads and messages.
"""

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
from core.responses import error_response
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
    """Pagination configuration for thread listings.

    The pagination behaviour is defined on a dedicated class to keep the
    ``ThreadViewSet`` readable while still exposing the knobs that influence
    page size.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ThreadViewSet(viewsets.GenericViewSet):
    """List and create messaging threads.

    The viewset keeps mutations limited to thread creation, while reads are
    paginated through ``ThreadPagination``. All heavy lifting is delegated to
    serializers, so the code here is mostly about orchestrating those helpers.
    """

    serializer_class = ThreadSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = ThreadPagination

    def get_queryset(self):
        """Return the threads visible to the requesting user.

        Returns:
            QuerySet[Thread]: Thread records ordered by last activity where the
            current user is either the collaborating organisation or the agent.
        """

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

    def list(self, request, *args, **kwargs):
        """Return a paginated list of threads for the current user.

        Args:
            request (Request): The HTTP request containing authentication
                context.
            *args: Unused positional parameters required by the DRF signature.
            **kwargs: Unused keyword parameters required by the DRF signature.

        Returns:
            Response: Paginated response with serialized threads.
        """

        del args, kwargs

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = ThreadSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        """Create a messaging thread after validating entitlement.

        Args:
            request (Request): The HTTP request with payload data.
            *args: Unused positional parameters required by DRF.
            **kwargs: Unused keyword parameters required by DRF.

        Returns:
            Response: The created thread serialized as JSON.
        """

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
            # Agents must satisfy a feature-flag-like requirement before they
            # can initiate new threads themselves.
            if not agent_meets_requirement(user, MESSAGING_INITIATE_REQUIREMENT):
                payload = requirement_denied_payload(
                    MESSAGING_INITIATE_REQUIREMENT,
                    "Permission denied.",
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)
        elif collaborator.user_id != user.id and not request.user.is_staff:
            return error_response(
                "Permission denied.",
                status.HTTP_403_FORBIDDEN,
                code="messaging_thread_permission_denied",
                collaborator_id=str(collaborator.id),
            )
        thread = serializer.save()
        output = ThreadSerializer(thread)
        return Response(output.data, status=status.HTTP_201_CREATED)


class ThreadMessagesPagination(PageNumberPagination):
    """Pagination configuration for thread message listings.

    Separate pagination from ``ThreadPagination`` to keep message listing
    responses lighter even when threads themselves use larger pages.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ThreadMessagesView(APIView):
    """List and create messages within a thread.

    The view groups ``GET`` and ``POST`` endpoints together so the thread lookup
    and permission checks are centralised in ``get_thread``.
    """

    permission_classes = (IsThreadParticipant,)
    pagination_class = ThreadMessagesPagination

    def get_thread(self, request, thread_id):
        """Return the requested thread if the user has access.

        Args:
            request (Request): Incoming HTTP request.
            thread_id (UUID): Identifier of the thread.

        Returns:
            Thread | None: The thread when accessible, otherwise ``None``.
        """

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
        """Paginate and return messages for the given thread.

        Args:
            request (Request): The HTTP request.
            thread_id (UUID): Identifier of the thread.

        Returns:
            Response: Paginated response containing serialized messages or an
            error payload if access is denied.
        """

        thread = self.get_thread(request, thread_id)
        if not thread:
            return error_response(
                "Thread not found or access denied.",
                status.HTTP_404_NOT_FOUND,
                code="messaging_thread_not_accessible",
                thread_id=str(thread_id),
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
        """Create a new message within the specified thread.

        Args:
            request (Request): The HTTP request containing message payload.
            thread_id (UUID): Identifier of the thread that receives the
                message.

        Returns:
            Response: Serialized message data after creation.
        """

        thread = self.get_thread(request, thread_id)
        if not thread:
            return error_response(
                "Thread not found or access denied.",
                status.HTTP_404_NOT_FOUND,
                code="messaging_thread_not_accessible",
                thread_id=str(thread_id),
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
    """Toggle read state for a specific message.

    This view is intentionally limited to a ``PATCH`` handler to make the
    intent clear: only partial updates to the ``is_read`` flag are supported.
    """

    permission_classes = (IsThreadParticipant,)

    def patch(self, request, message_id):
        """Update the message read status when the user participates in the thread.

        Args:
            request (Request): The HTTP request containing the update payload.
            message_id (UUID): Identifier of the message being updated.

        Returns:
            Response: Serialized message data after the read state toggle or an
            error payload if validation fails.
        """

        message = (
            Message.objects.select_related(
                "thread__collaborator__user",
                "thread__agent__user",
            )
            .filter(id=message_id)
            .first()
        )
        if not message:
            return error_response(
                "Message not found.",
                status.HTTP_404_NOT_FOUND,
                code="messaging_message_not_found",
                message_id=str(message_id),
            )
        if not IsThreadParticipant().has_object_permission(request, self, message):
            return error_response(
                "Access denied.",
                status.HTTP_403_FORBIDDEN,
                code="messaging_message_access_denied",
                message_id=str(message_id),
            )

        if message.sender_id == request.user.id:
            return error_response(
                "Only the message recipient may update read status.",
                status.HTTP_403_FORBIDDEN,
                code="messaging_message_read_status_forbidden",
                message_id=str(message_id),
            )

        serializer = MessageReadSerializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MessageSerializer(message).data)
