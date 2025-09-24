"""Database models for messaging threads and messages.

The models remain intentionally small and lean on foreign keys to other apps so
that messaging can evolve independently from athlete or organisation features.
"""

import uuid

from django.conf import settings
from django.db import models

from athletes.models import Athlete
from organisations.models import Collaborator
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps.

    Attributes:
        id (UUIDField): Primary key used across messaging tables.
        created_at (DateTimeField): Creation timestamp managed by Django.
        updated_at (DateTimeField): Last modification timestamp.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django model configuration metadata."""

        abstract = True


class Thread(BaseModel):
    """Two-way conversation between a collaborator and an agent.

    Threads may optionally reference an athlete when the conversation is tied to
    a specific talent, but the relationship is nullable to support generic chat
    between collaborators and agents.
    """

    collaborator = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        related_name="threads",
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name="threads",
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="threads",
    )
    last_message_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        """Django model configuration metadata.

        The unique constraint prevents duplicate inbox conversations, while the
        indexes accelerate lookups filtered by participant or activity date.
        """

        constraints = [
            models.UniqueConstraint(
                fields=("collaborator", "agent", "athlete"),
                name="unique_thread_collaborator_agent_athlete",
            ),
        ]
        indexes = [
            models.Index(fields=("collaborator",), name="thread_collaborator_idx"),
            models.Index(fields=("agent",), name="thread_agent_idx"),
            models.Index(
                fields=("-last_message_at",), name="thread_last_message_desc_idx"
            ),
        ]

    def __str__(self):
        base = f"{self.collaborator} ↔ {self.agent}"
        if self.athlete:
            return f"{base} ({self.athlete})"
        return base


class Message(BaseModel):
    """Individual message sent within a thread.

    Attributes:
        thread (Thread): Parent conversation that owns the message.
        sender (User): User account who authored the message.
        content (str): Message body.
        attachment (File | None): Optional file upload.
        is_read (bool): Read receipt flag managed by recipients.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    content = models.TextField()
    attachment = models.FileField(
        upload_to="message_attachments/",
        blank=True,
        null=True,
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        """Django model configuration metadata.

        Ordering maintains chronological message flow, while indexes improve
        filtering by thread and read status.
        """

        indexes = [
            models.Index(
                fields=("thread", "created_at"), name="message_thread_created_idx"
            ),
            models.Index(fields=("is_read",), name="message_is_read_idx"),
        ]
        ordering = ("created_at",)

    def __str__(self):
        return f"Message from {self.sender} in {self.thread}"
