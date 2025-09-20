"""Minimal stub implementation for Django REST Framework integration."""


class DjangoFilterBackend:
    """No-op backend to satisfy DRF integration during tests."""

    def filter_queryset(self, request, queryset, view):
        """Return the queryset untouched."""

        return queryset
