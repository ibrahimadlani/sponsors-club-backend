"""Minimal stub implementation for Django REST Framework integration."""

# pylint: disable=too-few-public-methods,unused-argument


class DjangoFilterBackend:
    """No-op backend to satisfy DRF integration during tests."""

    def filter_queryset(self, request, queryset, view):
        """Return the queryset untouched."""

        return queryset
