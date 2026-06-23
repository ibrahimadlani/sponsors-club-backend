"""Permission helpers for the messaging application.

The classes here are lightweight so they can be reused by both viewsets and
function-based views without pulling in extra dependencies.
"""

from rest_framework import permissions

from .models import Thread


class IsThreadParticipant(permissions.BasePermission):
    """Grant access if the request user participates in the thread.

    The permission handles both thread instances and message instances by
    unwrapping the related thread when necessary. This mirrors the way the
    messaging endpoints expose nested resources.
    """

    def has_object_permission(self, request, view, obj):
        """Check object level permissions for messaging resources.

        Args:
            request (Request): Incoming request containing the authenticated
                user.
            view (APIView): The view requesting the permission check.
            obj (Thread | Message): The object to authorize against.

        Returns:
            bool: ``True`` when the user is either the collaborator or agent
            associated with the thread.
        """

        if isinstance(obj, Thread):
            thread = obj
        else:
            thread = getattr(obj, "thread", None)
            if thread is None:
                return False
        # Guard against anonymous users so we never leak object existence.
        user = request.user
        if not user or not user.is_authenticated:
            return False
        collaborator_user_id = getattr(thread.collaborator, "user_id", None)
        agent_user_id = getattr(thread.agent, "user_id", None)
        return user.id in {collaborator_user_id, agent_user_id}

    def has_permission(self, request, view):
        """Check basic authentication requirement.

        Args:
            request (Request): The incoming request.
            view (APIView): The view requesting the check.

        Returns:
            bool: ``True`` if the user is authenticated.
        """

        return bool(request.user and request.user.is_authenticated)
