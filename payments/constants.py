"""Shared constants for the payments application."""

# The admin panels and serializers rely on a consistent set of fields to display
# subscription plans. Keeping them in one tuple avoids mismatches across
# multiple modules.
PLAN_CORE_FIELDS = (
    "code",
    "name",
    "price",
    "currency",
    "max_athletes",
    "max_collaborators",
)
