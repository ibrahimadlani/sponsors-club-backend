"""Serializers exposing messaging threads and messages."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from athletes.models import Athlete
from organisations.models import Collaborator
from users.models import AgentProfile

from .models import Message, Thread


class CollaboratorSerializer(serializers.ModelSerializer):
    """Lightweight collaborator representation embedded in a thread."""

    class Meta:
        model = Collaborator
        fields = ("id", "user_id", "organisation_id", "role", "job_title")
        read_only_fields = fields


class AgentProfileSerializer(serializers.ModelSerializer):
    """Expose essential agent profile attributes for messaging responses."""

    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = AgentProfile
        fields = ("id", "user_id", "display_name")
        read_only_fields = fields


class AthleteSerializer(serializers.ModelSerializer):
    """Represent the athlete linked to a conversation when available."""

    class Meta:
        model = Athlete
        fields = ("id", "full_name", "sport_id")
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    """Serialize messages, handling creation and attachment URLs."""

    thread = serializers.PrimaryKeyRelatedField(read_only=True)
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    attachment = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "thread",
            "sender",
            "content",
            "attachment",
            "is_read",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "thread",
            "sender",
            "is_read",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "content": {"allow_blank": True, "required": False},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Ensure that a message contains textual content or an attachment."""

        content = (attrs.get("content") or "").strip()
        attachment = attrs.get("attachment")
        if not content and not attachment:
            raise serializers.ValidationError(
                {"content": _("A message requires text content or an attachment.")}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Message:
        """Persist a new message for the configured thread and request user."""

        request = self.context.get("request")
        thread: Thread | None = self.context.get("thread")
        if request is None or thread is None:
            raise AssertionError(
                "MessageSerializer requires request and thread context."
            )
        attachment = validated_data.pop("attachment", None)
        message = Message.objects.create(
            thread=thread,
            sender=request.user,
            attachment=attachment,
            **validated_data,
        )
        return message

    def to_representation(self, instance: Message) -> dict[str, Any]:
        """Render the attachment as an absolute URL when possible."""

        data = super().to_representation(instance)
        attachment = data.get("attachment")
        if attachment:
            request = self.context.get("request")
            if request is not None:
                data["attachment"] = request.build_absolute_uri(attachment)
        else:
            data["attachment"] = None
        return data


class ThreadSerializer(serializers.ModelSerializer):
    """Serialize a conversation with participant summaries and last message."""

    collaborator = CollaboratorSerializer(read_only=True)
    agent = AgentProfileSerializer(read_only=True)
    athlete = AthleteSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = (
            "id",
            "collaborator",
            "agent",
            "athlete",
            "last_message_at",
            "created_at",
            "updated_at",
            "last_message",
        )
        read_only_fields = fields

    def get_last_message(self, obj: Thread) -> dict[str, Any] | None:
        """Return the most recent message associated with the thread."""

        message: Message | None = None
        prefetched = getattr(obj, "_last_message_list", None)
        if prefetched:
            message = prefetched[0]
        elif hasattr(obj, "_last_message"):
            message = getattr(obj, "_last_message")
        else:
            message = obj.messages.order_by("-created_at").first()
        if not message:
            return None
        serializer = MessageSerializer(message, context=self.context)
        return serializer.data
