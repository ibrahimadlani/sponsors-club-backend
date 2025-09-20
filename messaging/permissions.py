"""Permission helpers for the messaging application."""


from rest_framework import permissions

from .models import Thread


class IsThreadParticipant(permissions.BasePermission):
    """Grant access if the request user participates in the thread."""

    def has_object_permission(self, request, view, obj):
        """Check object level permissions for messaging resources."""

        if isinstance(obj, Thread):
            thread = obj
        else:
            thread = getattr(obj, 'thread', None)
            if thread is None:
                return False
        user = request.user
        if not user or not user.is_authenticated:
            return False
        collaborator_user_id = getattr(thread.collaborator, 'user_id', None)
        agent_user_id = getattr(thread.agent, 'user_id', None)
        return user.id in {collaborator_user_id, agent_user_id}

    def has_permission(self, request, view):
        """Check basic authentication requirement."""

        return bool(request.user and request.user.is_authenticated)
