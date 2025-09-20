"""Serializers for messaging threads and messages."""


from django.db import transaction
from rest_framework import serializers

from athletes.models import Athlete
from organisations.models import Collaborator
from users.models import AgentProfile

from .constants import THREAD_PARTICIPANT_COLUMNS
from .models import Message, Thread


class CollaboratorSummarySerializer(serializers.ModelSerializer):
    """Lightweight collaborator representation for thread payloads."""

    class Meta:
        """Serializer configuration."""

        model = Collaborator
        fields = ('id', 'organisation_id', 'role')
        ref_name = 'MessagingCollaboratorSummary'


class AgentProfileSummarySerializer(serializers.ModelSerializer):
    """Expose core agent profile fields for thread payloads."""

    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        """Serializer configuration."""

        model = AgentProfile
        fields = ('id', 'display_name', 'user_email')
        ref_name = 'MessagingAgentSummary'


class AthleteSummarySerializer(serializers.ModelSerializer):
    """Expose the subset of athlete data used within messaging threads."""

    class Meta:
        """Serializer configuration."""

        model = Athlete
        fields = ('id', 'full_name', 'sport_id')
        ref_name = 'MessagingAthleteSummary'


class ThreadSerializer(serializers.ModelSerializer):
    """Serialize thread entities with related participant summaries."""

    collaborator = CollaboratorSummarySerializer(read_only=True)
    agent = AgentProfileSummarySerializer(read_only=True)
    athlete = AthleteSummarySerializer(read_only=True)

    class Meta:
        """Serializer configuration."""

        model = Thread
        fields = ('id', *THREAD_PARTICIPANT_COLUMNS, 'updated_at')
        read_only_fields = fields


class ThreadCreateSerializer(serializers.Serializer):
    """Validate payload required to open a messaging thread."""

    collaborator_id = serializers.UUIDField(required=False)
    agent_id = serializers.UUIDField(required=False)
    athlete_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        """Ensure collaborator, agent, and optional athlete inputs are consistent."""

        request = self.context['request']
        user = request.user

        collaborator = None
        agent = None
        athlete = None

        collaborator_id = attrs.get('collaborator_id')
        agent_id = attrs.get('agent_id')
        athlete_id = attrs.get('athlete_id')

        if collaborator_id:
            collaborator = (
                Collaborator.objects.filter(id=collaborator_id)
                .select_related('user')
                .first()
            )
            if not collaborator:
                raise serializers.ValidationError({'collaborator_id': 'Collaborator not found.'})
        if agent_id:
            agent = AgentProfile.objects.filter(id=agent_id).select_related('user').first()
            if not agent:
                raise serializers.ValidationError({'agent_id': 'Agent not found.'})
        if athlete_id:
            athlete = Athlete.objects.filter(id=athlete_id).first()
            if not athlete:
                raise serializers.ValidationError({'athlete_id': 'Athlete not found.'})

        # Determine collaborator and agent based on requesting user if not provided
        if collaborator is None:
            collaborator = Collaborator.objects.filter(user=user).first()
        if agent is None:
            try:
                agent = user.agent_profile
            except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
                agent = None

        if collaborator is None or agent is None:
            raise serializers.ValidationError(
                'A collaborator and an agent must be specified.'
            )

        if user.id not in {collaborator.user_id, agent.user_id}:
            raise serializers.ValidationError(
                'User must represent either the collaborator or the agent.'
            )

        attrs['collaborator'] = collaborator
        attrs['agent'] = agent
        attrs['athlete'] = athlete

        # Prevent duplicate threads
        existing = Thread.objects.filter(
            collaborator=collaborator,
            agent=agent,
            athlete=athlete,
        ).exists()
        if existing:
            raise serializers.ValidationError('Thread already exists for these participants.')

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Persist a new thread based on validated participant data."""

        collaborator = validated_data['collaborator']
        agent = validated_data['agent']
        athlete = validated_data['athlete']
        thread = Thread.objects.create(
            collaborator=collaborator,
            agent=agent,
            athlete=athlete,
        )
        return thread

    def update(self, instance, validated_data):
        """Thread updates are not supported for this serializer."""

        raise NotImplementedError('Thread updates are not supported.')


class MessageSerializer(serializers.ModelSerializer):
    """Serialize individual messages, exposing sender metadata."""

    sender_email = serializers.EmailField(source='sender.email', read_only=True)

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = (
            'id',
            'thread',
            'sender',
            'sender_email',
            'content',
            'attachment',
            'is_read',
            'created_at',
        )
        read_only_fields = ('id', 'thread', 'sender', 'sender_email', 'created_at')


class MessageCreateSerializer(serializers.ModelSerializer):
    """Validate and create outbound messages for a thread."""

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = ('content', 'attachment')

    def validate(self, attrs):
        """Ensure a message includes content or an attachment."""

        content = attrs.get('content', '').strip()
        if not content and not attrs.get('attachment'):
            raise serializers.ValidationError('Message must contain content or an attachment.')
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create the message, updating the thread last-message timestamp."""

        thread = self.context['thread']
        sender = self.context['request'].user
        message = Message.objects.create(
            thread=thread,
            sender=sender,
            **validated_data,
        )
        thread.last_message_at = message.created_at
        thread.save(update_fields=['last_message_at', 'updated_at'])
        return message


class MessageReadSerializer(serializers.ModelSerializer):
    """Toggle the read state of a message."""

    class Meta:
        """Serializer configuration."""

        model = Message
        fields = ('is_read',)

    def update(self, instance, validated_data):
        """Persist the new read state."""

        instance.is_read = validated_data.get('is_read', True)
        instance.save(update_fields=['is_read', 'updated_at'])
        return instance
