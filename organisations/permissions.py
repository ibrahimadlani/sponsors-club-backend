"""Custom permission classes for organisation endpoints."""

from rest_framework import permissions

from .models import Collaborator


class IsCollaboratorAccount(permissions.BasePermission):
    """Allow access only to users whose account type is collaborator or staff."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return getattr(request.user, 'account_type', None) == request.user.AccountType.COLLABORATOR


class IsAuthenticatedCollaborator(permissions.BasePermission):
    """Allow access if the user is a collaborator of the organisation."""

    def has_permission(self, request, view):
        """Return True when the request user collaborates with the organisation."""
        organisation = getattr(view, 'organisation', None)
        if not request.user or not request.user.is_authenticated:
            # Let IsAuthenticated handle authentication failures.
            return True
        if organisation is None:
            return False
        return Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
        ).exists()


class IsOrganisationOwner(permissions.BasePermission):
    """Allow access only to organisation owner collaborators."""

    def has_permission(self, request, view):
        """Return True when the request user owns the organisation."""
        organisation = getattr(view, 'organisation', None)
        if organisation is None:
            return False
        return Collaborator.objects.filter(
            organisation=organisation,
            user=request.user,
            role=Collaborator.Role.OWNER,
        ).exists()
