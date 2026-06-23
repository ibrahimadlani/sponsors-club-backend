"""Permission helpers specific to athlete endpoints.

Permissions encapsulate access rules so that views remain declarative and easy
to audit independently from the data layer.

Two permission families coexist:
* **Legacy** (``IsAgentUser``, ``IsCollaboratorUser``, ``CanViewAthlete``,
  ``IsAthleteOwner``) — based on the original ``AgentProfile`` model.  Kept
  for backward compatibility with existing views.
* **Entourage** (``IsAthleteOrAuthorizedRepresentative``) — based on the new
  ``RepresentationMandate`` system.  Views opt in by declaring a
  ``required_mandate_permission`` class attribute.
"""

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


class IsAthleteOrAuthorizedRepresentative(permissions.BasePermission):
    """Grant object-level access based on the entourage mandate system.

    A request is authorised when **any** of the following is true:

    1. The user is a Django staff member or superuser.
    2. The user is the ``AgentProfile`` owner of the athlete (legacy path,
       preserved for backward compatibility until the full migration is
       complete).
    3. The user holds an **active** ``RepresentationMandate`` for the athlete
       whose permission flag matching ``required_mandate_permission`` is
       ``True``.

    Usage in a view::

        class AthleteMessagingView(APIView):
            permission_classes = [IsAuthenticated, IsAthleteOrAuthorizedRepresentative]
            required_mandate_permission = "can_manage_messaging"

    The ``required_mandate_permission`` attribute must name one of the three
    boolean flags on ``RepresentationMandate``:

    * ``"can_manage_messaging"`` — reply to sponsors in the messaging module.
    * ``"can_negotiate_contracts"`` — edit and counter-propose contract clauses.
    * ``"can_sign_legally"`` — sign contracts with legal effect.

    When the attribute is absent from the view, ``"can_manage_messaging"`` is
    used as a safe default.
    """

    # Default permission flag checked when the view does not specify one.
    _DEFAULT_PERMISSION = "can_manage_messaging"

    # All valid flag names, used to guard against misconfigured views.
    _VALID_PERMISSIONS = frozenset(
        {"can_manage_messaging", "can_negotiate_contracts", "can_sign_legally"}
    )

    def has_permission(self, request, view) -> bool:
        """Require authentication as a baseline.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View requesting permission.

        Returns:
            bool: ``True`` when the user is authenticated.
        """
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        """Evaluate whether the user may act on the given athlete object.

        The method resolves the required permission flag from the calling view,
        then walks the three grant paths described in the class docstring.

        Args:
            request (rest_framework.request.Request): Incoming HTTP request.
            view (rest_framework.views.APIView): View that owns this check.
            obj (athletes.models.Athlete): Athlete being accessed or mutated.

        Returns:
            bool: ``True`` when the user is authorised to proceed.
        """
        from .models import RepresentationMandate

        user = request.user

        # --- Path 1: staff bypass ---
        if user.is_staff or user.is_superuser:
            return True

        # --- Path 2: legacy agent ownership (backward compat) ---
        agent_profile = get_agent_profile(user)
        if agent_profile and obj.agent_id == agent_profile.id:
            return True

        # --- Path 3: entourage mandate ---
        permission_flag = getattr(
            view, "required_mandate_permission", self._DEFAULT_PERMISSION
        )
        if permission_flag not in self._VALID_PERMISSIONS:
            # Misconfigured view: fail closed.
            return False

        try:
            rep_profile = user.representative_profile
        except Exception:
            # User has no RepresentativeProfile — not part of any entourage.
            return False

        # A single database query: look for an active mandate for this athlete
        # where the representative is the current user and the required flag
        # is explicitly granted.  ``filter`` + ``exists`` is cheaper than
        # ``get`` because it short-circuits at the first matching row.
        return RepresentationMandate.objects.filter(
            athlete=obj,
            representative=rep_profile,
            is_active=True,
            **{permission_flag: True},
        ).exists()
