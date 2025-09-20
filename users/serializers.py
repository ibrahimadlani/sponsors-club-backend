"""Serializers supporting the users API endpoints."""

from django.db import transaction
from rest_framework import serializers

from organisations.models import Collaborator

from .models import AgentProfile, User


class UserSerializer(serializers.ModelSerializer):
    """Serialize the base user fields shared across endpoints."""

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "email_verified",
            "account_type",
            "is_active",
            "is_staff",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "account_type",
            "is_active",
            "is_staff",
            "created_at",
            "updated_at",
        )


class RegisterSerializer(serializers.ModelSerializer):
    """Handle registration for both agent and collaborator accounts."""

    password = serializers.CharField(write_only=True)
    display_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    organisation_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    job_title = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "account_type",
            "display_name",
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "organisation_name",
            "job_title",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        """Ensure required companion fields are provided per account type."""
        account_type = attrs.get("account_type", User.AccountType.AGENT)
        display_name = attrs.get("display_name")
        if account_type == User.AccountType.AGENT and not display_name:
            raise serializers.ValidationError(
                {"display_name": "This field is required for agent accounts."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create a user and any related agent or collaborator records."""
        display_name = validated_data.pop("display_name", None)
        validated_data.pop("organisation_name", None)
        validated_data.pop("job_title", None)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        if user.account_type == User.AccountType.AGENT:
            default_display_name = (
                f"{user.first_name} {user.last_name}".strip() or user.email
            )
            AgentProfile.objects.create(
                user=user,
                display_name=display_name or default_display_name,
            )
        return user

    def to_representation(self, instance):
        """Use the base user serializer for the outward representation."""
        return UserSerializer(instance, context=self.context).data


class MeUpdateSerializer(serializers.ModelSerializer):
    """Allow the authenticated user to update their profile details."""

    display_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "display_name",
        )

    def update(self, instance, validated_data):
        """Update the user object and related agent profile when needed."""
        display_name = validated_data.pop("display_name", None)
        update_fields = []
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            update_fields.append(attr)
        if update_fields:
            update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
        else:
            instance.save()

        if display_name is not None and instance.account_type == User.AccountType.AGENT:
            agent_profile, _ = AgentProfile.objects.get_or_create(
                user=instance,
            )
            agent_profile.display_name = display_name
            agent_profile.save(update_fields=["display_name"])

        return instance

    def to_representation(self, instance):
        """Augment the serialized representation with agent info when relevant."""
        data = UserSerializer(instance, context=self.context).data
        if instance.account_type == User.AccountType.AGENT:
            try:
                agent_profile = instance.agent_profile
            except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
                agent_profile = None
            if agent_profile is not None:
                data["agent_profile"] = {
                    "id": str(agent_profile.id),
                    "display_name": agent_profile.display_name,
                }
        return data


class RolesSerializer(serializers.Serializer):
    """Represent the various collaborations and agent details for a user."""

    is_agent = serializers.BooleanField()
    agent_profile = serializers.DictField(allow_null=True)
    collaborations = serializers.ListField(child=serializers.DictField())

    def create(self, validated_data):
        """Disallow creation via this read-only serializer."""
        raise NotImplementedError("RolesSerializer is read-only.")

    def update(self, instance, validated_data):
        """Disallow updates via this read-only serializer."""
        raise NotImplementedError("RolesSerializer is read-only.")


class RolesDataBuilder:
    """Utility for building the /me/roles response payload."""

    def __init__(self, user):
        """Store the user for later role aggregation."""
        self.user = user

    def build(self):
        """Construct the payload expected by `RolesSerializer`."""
        agent_info = None
        try:
            agent_profile = self.user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
            agent_profile = None
        if agent_profile is not None:
            agent_info = {
                "id": str(agent_profile.id),
                "display_name": agent_profile.display_name,
            }

        collaborations = [
            {
                "id": str(collaboration.id),
                "organisation_id": str(collaboration.organisation_id),
                "organisation_name": collaboration.organisation.name,
                "role": collaboration.role,
            }
            for collaboration in Collaborator.objects.filter(
                user=self.user
            ).select_related("organisation")
        ]

        return {
            "is_agent": agent_info is not None,
            "agent_profile": agent_info,
            "collaborations": collaborations,
        }
