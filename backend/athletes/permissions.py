"""Permission helpers specific to athlete endpoints."""

from rest_framework import permissions

from core.permissions import (
    get_agent_profile,
    user_is_agent,
    user_is_collaborator,
)


class IsAgentUser(permissions.BasePermission):
    """Allow access only to authenticated agent accounts with a profile."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not user_is_agent(request.user):
            return False
        return get_agent_profile(request.user) is not None


class IsCollaboratorUser(permissions.BasePermission):
    """Allow access only to authenticated collaborator accounts."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_is_collaborator(request.user)


class CanViewAthlete(permissions.BasePermission):
    """Allow retrieval for the owning agent or any collaborator account."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        agent_profile = get_agent_profile(request.user)
        if agent_profile and obj.agent_id == agent_profile.id:
            return True
        return user_is_collaborator(request.user)


class IsAthleteOwner(permissions.BasePermission):
    """Allow modifications only for the agent who owns the athlete."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        agent_profile = get_agent_profile(request.user)
        if not agent_profile:
            return False
        return obj.agent_id == agent_profile.id
