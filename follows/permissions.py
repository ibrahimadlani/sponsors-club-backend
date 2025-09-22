"""Custom permission classes used by the follows API endpoints."""

from rest_framework import permissions

from organisations.models import Collaborator


class IsCollaboratorUser(permissions.BasePermission):
    """Ensure the requesting user is linked to at least one collaborator.

    The views allow users to act on behalf of their organisations, so we need
    to make sure the authenticated account actually has a collaborator
    relationship. That check is centralised here to keep the views focused on
    business logic.
    """

    def has_permission(self, request, view):
        """Return whether the request should be granted access.

        Args:
            request: Incoming HTTP request sent by the API client.
            view: The view attempting to evaluate permissions. This parameter
                is unused but included to match Django REST Framework's API.

        Returns:
            bool: ``True`` when the user is authenticated and linked to at
            least one :class:`organisations.models.Collaborator` record.
        """

        if not request.user or not request.user.is_authenticated:
            return False

        # Collaborator membership is stored as a separate model referencing the
        # user. Existence of at least one record proves the user has access to
        # organisation-level follow features.
        return Collaborator.objects.filter(user=request.user).exists()
