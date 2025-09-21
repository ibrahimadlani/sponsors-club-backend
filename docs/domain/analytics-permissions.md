# Analytics permissions

`analytics.permissions.IsAgentOrStaff` centralises write-access rules for the
analytics domain. It allows any authenticated user to perform read-only
operations but restricts unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) to
agent accounts with an `AgentProfile` or staff/superuser accounts.

The permission works by:
1. Rejecting unauthenticated requests outright.
2. Returning `True` for safe methods to keep analytics read endpoints broadly
   accessible.
3. Granting access when `request.user.is_staff` or `is_superuser` is true.
4. Attempting to load `request.user.agent_profile`; if the related
   `AgentProfile` is missing a `DoesNotExist` exception is handled and the check
   fails.

Use this permission on any analytics views that mutate resources (e.g.
admin-only sync triggers) or when exposing future write APIs for agent-managed
analytics data.
