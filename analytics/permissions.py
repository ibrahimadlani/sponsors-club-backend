"""Permission helpers for analytics endpoints."""

from rest_framework import permissions

from users.models import AgentProfile


class IsAgentOrStaff(permissions.BasePermission):
    """Allow only agent users or staff to perform write operations."""

    def has_permission(self, request, view):
        """Check whether the authenticated user can access the endpoint.

        Args:
            request: Incoming HTTP request bound to the permission check.
            view: View instance requesting permission evaluation.

        Returns:
            bool: ``True`` when the user can proceed, ``False`` otherwise.
        """

        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            # Read-only operations are allowed for any authenticated user.
            return True
        if request.user.is_staff or request.user.is_superuser:
            # Staff members retain full access regardless of role assignments.
            return True
        try:
            request.user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
            return False
        return True
