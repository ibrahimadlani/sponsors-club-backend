"""Permission helpers specific to athlete endpoints."""

# Permissions encapsulate who can read or edit athlete data so the views stay
# declarative and easy to audit.

from rest_framework import permissions

from core.permissions import (
    get_agent_profile,
    user_is_agent,
    user_is_collaborator,
)


class IsAgentUser(permissions.BasePermission):
    """Allow access only to authenticated agent accounts with a profile."""

    def has_permission(self, request, view):
        """Validate that the user is an agent with an attached profile.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View requesting permission.

        Returns:
            bool: ``True`` when the user is authenticated and has an agent
            profile, otherwise ``False``.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        if not user_is_agent(request.user):
            return False
        # A missing profile indicates onboarding is incomplete.
        return get_agent_profile(request.user) is not None


class IsCollaboratorUser(permissions.BasePermission):
    """Allow access only to authenticated collaborator accounts."""

    def has_permission(self, request, view):
        """Check whether the user is a collaborator account.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View requesting permission.

        Returns:
            bool: ``True`` for authenticated collaborator users.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        return user_is_collaborator(request.user)


class CanViewAthlete(permissions.BasePermission):
    """Allow retrieval for the owning agent or any collaborator account."""

    def has_object_permission(self, request, view, obj):
        """Restrict athlete visibility to permitted users.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View requesting permission.
            obj (athletes.models.Athlete): Athlete being accessed.

        Returns:
            bool: ``True`` if the user can view the athlete record.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        agent_profile = get_agent_profile(request.user)
        if agent_profile and obj.agent_id == agent_profile.id:
            return True
        # Fallback to collaborator-level visibility when the agent does not own
        # the athlete.
        return user_is_collaborator(request.user)


class IsAthleteOwner(permissions.BasePermission):
    """Allow modifications only for the agent who owns the athlete."""

    def has_object_permission(self, request, view, obj):
        """Ensure only the owning agent can mutate the athlete.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View requesting permission.
            obj (athletes.models.Athlete): Athlete being modified.

        Returns:
            bool: ``True`` when the requesting agent owns the athlete.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        agent_profile = get_agent_profile(request.user)
        if not agent_profile:
            return False
        return obj.agent_id == agent_profile.id
