"""Serializers for messaging threads and messages."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from athletes.models import Athlete
from organisations.models import Collaborator
from users.models import AgentProfile

from .models import Message, Thread


class CollaboratorSerializer(serializers.ModelSerializer):
    """Expose collaborator information for thread payloads."""

    user = serializers.UUIDField(source="user_id", read_only=True)

    class Meta:
        model = Collaborator
        fields = ("id", "user", "organisation_id", "role", "job_title")
        read_only_fields = fields


class AgentProfileSerializer(serializers.ModelSerializer):
    """Expose core agent profile data for thread payloads."""

    user = serializers.UUIDField(source="user_id", read_only=True)

    class Meta:
        model = AgentProfile
        fields = ("id", "user", "display_name")
        read_only_fields = fields


class AthleteSerializer(serializers.ModelSerializer):
    """Return a trimmed representation of the athlete linked to the thread."""

    class Meta:
        model = Athlete
        fields = ("id", "full_name", "sport_id")
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    """Serialize individual messages and handle attachment URLs."""

    thread = serializers.UUIDField(source="thread_id", read_only=True)
    sender = serializers.UUIDField(source="sender_id", read_only=True)
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
        read_only_fields = ("id", "thread", "sender", "is_read", "created_at", "updated_at")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Ensure that either text content or an attachment is provided."""

        content = attrs.get("content", "").strip()
        attachment = attrs.get("attachment")
        if not content and not attachment:
            raise serializers.ValidationError(
                {"content": "A message must include text or an attachment."}
            )
        attrs["content"] = content
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Message:
        """Persist a new message on the thread from the current user."""

        request = self.context.get("request")
        thread: Thread | None = self.context.get("thread")
        if not request or not thread:
            raise AssertionError("MessageSerializer requires request and thread in context.")

        message = Message.objects.create(
            thread=thread,
            sender=request.user,
            **validated_data,
        )
        Thread.objects.filter(id=thread.id).update(last_message_at=message.created_at)
        return message

    def update(self, instance: Message, validated_data: dict[str, Any]) -> Message:
        """Update mutable message fields."""

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=list(validated_data.keys()))
        return instance

    def to_representation(self, instance: Message) -> dict[str, Any]:
        """Return a representation with a fully qualified attachment URL when available."""

        data = super().to_representation(instance)
        attachment = instance.attachment
        if attachment:
            request = self.context.get("request")
            url = attachment.url
            if request is not None:
                url = request.build_absolute_uri(url)
            data["attachment"] = url
        else:
            data["attachment"] = None
        return data


class ThreadSerializer(serializers.ModelSerializer):
    """Serialize threads with participant summaries and the latest message."""

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
        """Return the most recent message in the thread, if any."""

        last_message = None
        if hasattr(obj, "last_message_list") and obj.last_message_list:
            last_message = obj.last_message_list[0]
        else:
            last_message = obj.messages.select_related("sender").order_by("-created_at").first()
        if not last_message:
            return None
        serializer = MessageSerializer(last_message, context=self.context)
        return serializer.data
