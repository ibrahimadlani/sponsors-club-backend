"""Serializers for messaging threads and messages.

Serializers in this module focus on shaping messaging payloads and validating
thread creation rules. Inline comments call out non-obvious business rules such
as de-duplication and access restrictions.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from rest_framework import serializers

from athletes.models import Athlete
from follows.models import Follow
from organisations.models import Collaborator
from users.models import AgentProfile

from .constants import THREAD_PARTICIPANT_COLUMNS
from .models import Message, Thread


def _safe_media_url(value):
    """Return a URL or file name for a media value when available."""

    if not value:
        return None
    if hasattr(value, "url"):
        try:
            return value.url
        except ValueError:
            return value.name
    if isinstance(value, str):
        return value
    return None


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    """Lightweight collaborator representation for thread payloads.

    The summary serializer keeps responses compact while still giving enough
    context to render collaborator information in a client UI.
    """

    first_name = serializers.CharField(
        source="user.first_name", read_only=True, allow_blank=True
    )
    last_name = serializers.CharField(
        source="user.last_name", read_only=True, allow_blank=True
    )
    organisation_name = serializers.CharField(
        source="organisation.name", read_only=True
    )
    avatar = serializers.SerializerMethodField()

    class Meta:
        """Serializer configuration."""

        model = Collaborator
        fields = (
            "id",
            "organisation_id",
            "role",
            "first_name",
            "last_name",
            "organisation_name",
            "avatar",
        )
        ref_name = "MessagingCollaboratorSummary"

    def get_avatar(self, obj):
        """Return the collaborator avatar when a media file is linked."""

        user = getattr(obj, "user", None)
        if user is None:
            return None

        direct_avatar = getattr(user, "avatar", None)
        if direct_avatar:
            media_url = _safe_media_url(direct_avatar)
            if media_url:
                return media_url

        avatar_method = getattr(user, "get_avatar_url", None)
        if callable(avatar_method):
            return avatar_method()

        return None


class AgentProfileSummarySerializer(serializers.ModelSerializer):
    """Expose core agent profile fields for thread payloads.

    Exposing the agent email is helpful for audit trails and debugging so it is
    denormalised here even though the ``AgentProfile`` already references the
    underlying user.
    """

    name = serializers.CharField(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        """Serializer configuration."""

        model = AgentProfile
        fields = ("id", "name", "user_email", "is_self_represented", "avatar")
        ref_name = "MessagingAgentSummary"

    def get_avatar(self, obj):
        """Return the agent profile avatar when available."""

        direct_avatar = getattr(obj, "avatar", None)
        media_url = _safe_media_url(direct_avatar)
        if media_url:
            return media_url

        user = getattr(obj, "user", None)
        if user is None:
            return None

        user_avatar = getattr(user, "avatar", None)
        media_url = _safe_media_url(user_avatar)
        if media_url:
            return media_url

        avatar_method = getattr(user, "get_avatar_url", None)
        if callable(avatar_method):
            return avatar_method()

        return None


class AthleteSummarySerializer(serializers.ModelSerializer):
    """Expose the subset of athlete data used within messaging threads.

    Messaging only needs lightweight context, so the serializer deliberately
    sticks to three columns to avoid needless database joins in consumers.
    """

    sport_name = serializers.CharField(source="sport.name", read_only=True)
    sport_emoji = serializers.CharField(
        source="sport.emoji", read_only=True, allow_null=True, allow_blank=True
    )

    class Meta:
        """Serializer configuration."""

        model = Athlete
        fields = ("id", "full_name", "sport_id", "sport_name", "sport_emoji", "avatar")
        ref_name = "MessagingAthleteSummary"


class ThreadSerializer(serializers.ModelSerializer):
    """Serialize thread entities with related participant summaries.

    The serializer is read-only and combines each participant summary to form a
    cohesive payload that matches the needs of the frontend inbox.
    """

    collaborator = CollaboratorSummarySerializer(read_only=True)
    agent = AgentProfileSummarySerializer(read_only=True)
    athlete = AthleteSummarySerializer(read_only=True)
    subtitle = serializers.SerializerMethodField()
    avatar_badge_emoji = serializers.SerializerMethodField()
    unread_messages_count = serializers.SerializerMethodField()

    class Meta:
        """Serializer configuration."""

        model = Thread
        fields = (
            "id",
            *THREAD_PARTICIPANT_COLUMNS,
            "updated_at",
            "unread_messages_count",
            "subtitle",
            "avatar_badge_emoji",
        )
        read_only_fields = fields

    def get_subtitle(self, obj):
        """Return the subtitle depending on the requesting user's role."""

        request = self.context.get("request")
        if not request:
            return None

        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None

        collaborator = getattr(obj, "collaborator", None)
        if collaborator and collaborator.user_id == getattr(user, "id", None):
            agent = getattr(obj, "agent", None)
            agent_name = getattr(agent, "name", None)
            if agent_name:
                return f"Représenté par {agent_name}"
        return None

    def get_avatar_badge_emoji(self, obj):
        """Expose the sport emoji to render as an avatar badge when available."""

        athlete = getattr(obj, "athlete", None)
        if not athlete:
            return None
        sport = getattr(athlete, "sport", None)
        emoji = getattr(sport, "emoji", None)
        return emoji or None

    def get_unread_messages_count(self, obj):
        """Return the unread message count annotated on the thread."""

        value = getattr(obj, "unread_messages_count", None)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class ThreadCreateSerializer(serializers.Serializer):
    """Validate payload required to open a messaging thread.

    Only collaborators and agents that the current user represents may create a
    thread. The serializer enforces those constraints before the view attempts
    persistence.
    """

    collaborator_id = serializers.UUIDField(required=False)
    agent_id = serializers.UUIDField(required=False)
    athlete_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        """Ensure collaborator, agent, and optional athlete inputs are consistent.

        Args:
            attrs (dict): Raw attributes for collaborator, agent, and athlete IDs.

        Raises:
            serializers.ValidationError: If participants cannot be resolved or
                the user is not authorised to create the thread.

        Returns:
            dict: Mutated attributes including hydrated participant instances.
        """

        request = self.context["request"]
        user = request.user

        collaborator = None
        agent = None
        athlete = None

        collaborator_id = attrs.get("collaborator_id")
        agent_id = attrs.get("agent_id")
        athlete_id = attrs.get("athlete_id")

        if collaborator_id:
            collaborator = (
                Collaborator.objects.filter(id=collaborator_id)
                .select_related("user")
                .first()
            )
            if not collaborator:
                raise serializers.ValidationError(
                    {"collaborator_id": "Collaborator not found."}
                )
        if agent_id:
            agent = (
                AgentProfile.objects.filter(id=agent_id).select_related("user").first()
            )
            if not agent:
                raise serializers.ValidationError({"agent_id": "Agent not found."})
        if athlete_id:
            athlete = Athlete.objects.filter(id=athlete_id).first()
            if not athlete:
                raise serializers.ValidationError({"athlete_id": "Athlete not found."})

        # Determine collaborator and agent based on requesting user if not provided.
        if collaborator is None:
            collaborator = Collaborator.objects.filter(user=user).first()
        if agent is None:
            try:
                agent = user.agent_profile
            except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
                agent = None

        if collaborator is None or agent is None:
            raise serializers.ValidationError(
                "A collaborator and an agent must be specified."
            )

        if user.id not in {collaborator.user_id, agent.user_id}:
            raise serializers.ValidationError(
                "User must represent either the collaborator or the agent."
            )

        if (
            athlete is not None
            and collaborator is not None
            and user.id == collaborator.user_id
        ):
            follows_athlete = Follow.objects.filter(
                collaborator=collaborator,
                athlete=athlete,
            ).exists()
            if not follows_athlete:
                raise serializers.ValidationError(
                    {"athlete_id": "Collaborateur doit suivre cet athlète pour démarrer une conversation."}
                )

        attrs["collaborator"] = collaborator
        attrs["agent"] = agent
        attrs["athlete"] = athlete

        # Prevent duplicate threads so the inbox never displays multiple
        # conversations for the same participants.
        existing = Thread.objects.filter(
            collaborator=collaborator,
            agent=agent,
            athlete=athlete,
        ).exists()
        if existing:
            raise serializers.ValidationError(
                "Thread already exists for these participants."
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Persist a new thread based on validated participant data.

        Args:
            validated_data (dict): Hydrated participant objects.

        Returns:
            Thread: Newly created thread instance.
        """

        collaborator = validated_data["collaborator"]
        agent = validated_data["agent"]
        athlete = validated_data["athlete"]
        thread = Thread.objects.create(
            collaborator=collaborator,
            agent=agent,
            athlete=athlete,
        )
        return thread

    def update(self, instance, validated_data):
        """Thread updates are not supported for this serializer.

        Raises:
            NotImplementedError: Always raised to signal that updates are not
                available.
        """

        raise NotImplementedError("Thread updates are not supported.")


class MessageSerializer(serializers.ModelSerializer):
    """Serialize individual messages while exposing sender metadata.

    The serializer is used for both list and detail responses. It appends a
    ``sender_email`` field so clients do not have to perform additional
    lookups.
    """

    thread = serializers.UUIDField(source="thread_id", read_only=True)
    sender = serializers.UUIDField(source="sender_id", read_only=True)
    sender_email = serializers.EmailField(source="sender.email", read_only=True)

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = (
            "id",
            "thread",
            "sender",
            "sender_email",
            "content",
            "attachment",
            "is_read",
            "created_at",
        )
        read_only_fields = ("id", "thread", "sender", "sender_email", "created_at")


class MessageCreateSerializer(serializers.ModelSerializer):
    """Validate and create outbound messages for a thread.

    The serializer expects the surrounding view to provide ``thread`` and
    ``request`` in the context so it can assign ownership and update timestamps.
    """

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = ("content", "attachment")

    def validate(self, attrs):
        """Ensure a message includes content or an attachment.

        Args:
            attrs (dict): Submitted message payload.

        Raises:
            serializers.ValidationError: If both content and attachment are
                missing.

        Returns:
            dict: The original attributes, untouched.
        """

        content = attrs.get("content", "").strip()
        if not content and not attrs.get("attachment"):
            raise serializers.ValidationError(
                "Message must contain content or an attachment."
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create the message, updating the thread last-message timestamp.

        Args:
            validated_data (dict): Sanitised message payload.

        Returns:
            Message: Newly persisted message instance.
        """

        thread = self.context["thread"]
        sender = self.context["request"].user
        message = Message.objects.create(
            thread=thread,
            sender=sender,
            **validated_data,
        )
        thread.last_message_at = message.created_at
        thread.save(update_fields=["last_message_at", "updated_at"])
        channel_layer = get_channel_layer()
        if channel_layer:
            payload = MessageSerializer(message).data
            async_to_sync(channel_layer.group_send)(
                f"thread_{thread.id}",
                {"type": "message_created", "payload": payload},
            )
        return message


class MessageReadSerializer(serializers.ModelSerializer):
    """Toggle the read state of a message.

    The serializer only handles the ``is_read`` flag to ensure we do not
    accidentally expose other fields for partial updates.
    """

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = ("is_read",)

    def update(self, instance, validated_data):
        """Persist the new read state.

        Args:
            instance (Message): Message instance to update.
            validated_data (dict): Attributes containing the desired read state.

        Returns:
            Message: Updated instance for chaining.
        """

        instance.is_read = validated_data.get("is_read", True)
        instance.save(update_fields=["is_read", "updated_at"])
        channel_layer = get_channel_layer()
        if channel_layer:
            payload = MessageSerializer(instance).data
            async_to_sync(channel_layer.group_send)(
                f"thread_{instance.thread_id}",
                {"type": "message_read", "payload": payload},
            )
        return instance
