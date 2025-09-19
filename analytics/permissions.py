"""Permission helpers for analytics endpoints."""

from rest_framework import permissions

from users.models import AgentProfile


class IsAgentOrStaff(permissions.BasePermission):  # pylint: disable=too-few-public-methods
    """Allow only agent users or staff to perform write operations."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_staff or request.user.is_superuser:
            return True
        try:
            request.user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]  # pylint: disable=no-member
            return False
        return True
