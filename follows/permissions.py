"""Custom permission classes for the follows API."""

# pylint: disable=no-member

from rest_framework import permissions

from organisations.models import Collaborator


class IsCollaboratorUser(permissions.BasePermission):
    """Allow access only if the user has at least one collaborator membership."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return Collaborator.objects.filter(user=request.user).exists()
