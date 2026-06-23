"""Shared constants for the messaging application.

Constants are centralised to keep admin and serializer modules aligned without
introducing circular imports.
"""

THREAD_PARTICIPANT_COLUMNS = (
    "collaborator",
    "agent",
    "athlete",
    "last_message_at",
    "created_at",
)
