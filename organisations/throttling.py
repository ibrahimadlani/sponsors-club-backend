"""Custom throttling classes for organisation-related endpoints."""

from rest_framework.throttling import UserRateThrottle


class InviteCreateThrottle(UserRateThrottle):
    """Throttle invitation creation to prevent spam."""

    rate = "10/hour"
    scope = "invite_create"

    def wait(self):
        if not hasattr(self, "history"):
            return None
        return super().wait()


class InviteJoinThrottle(UserRateThrottle):
    """Throttle invitation usage to prevent brute force attacks."""

    rate = "20/hour"
    scope = "invite_join"

    def wait(self):
        if not hasattr(self, "history"):
            return None
        return super().wait()
