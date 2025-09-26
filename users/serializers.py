"""Serializers supporting the users API endpoints."""

from django.db import transaction
from rest_framework import serializers

from organisations.models import Collaborator

from .emails import send_email_verification
from .models import AgentProfile, EmailVerificationToken, User


class UserSerializer(serializers.ModelSerializer):
    """Serialize the base user fields shared across endpoints."""

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_country_code",
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
    is_self_represented = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
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
            "is_self_represented",
            "phone_country_code",
            "phone_number",
            "date_of_birth",
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
        is_self_represented = validated_data.pop("is_self_represented", False)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        if user.account_type == User.AccountType.AGENT:
            default_display_name = (
                f"{user.first_name} {user.last_name}".strip() or user.email
            )
            AgentProfile.objects.create(
                user=user,
                display_name=display_name or default_display_name,
                is_self_represented=is_self_represented,
            )
        send_email_verification(user)
        return user

    def to_representation(self, instance):
        """Use the base user serializer for the outward representation."""
        return UserSerializer(instance, context=self.context).data


class MeUpdateSerializer(serializers.ModelSerializer):
    """Allow the authenticated user to update their profile details."""

    display_name = serializers.CharField(required=False, allow_blank=True)
    is_self_represented = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "phone_country_code",
            "phone_number",
            "date_of_birth",
            "display_name",
            "is_self_represented",
        )

    def update(self, instance, validated_data):
        """Update the user object and related agent profile when needed."""
        display_name = validated_data.pop("display_name", None)
        is_self_represented = validated_data.pop("is_self_represented", None)
        update_fields = []
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            update_fields.append(attr)
        if update_fields:
            update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
        else:
            instance.save()

        if (
            instance.account_type == User.AccountType.AGENT
            and (display_name is not None or is_self_represented is not None)
        ):
            agent_profile, _ = AgentProfile.objects.get_or_create(
                user=instance,
            )
            profile_updates: list[str] = []
            if display_name is not None:
                agent_profile.display_name = display_name
                profile_updates.append("display_name")
            if is_self_represented is not None:
                agent_profile.is_self_represented = is_self_represented
                profile_updates.append("is_self_represented")
            if profile_updates:
                agent_profile.save(update_fields=profile_updates)
                agent_profile.refresh_from_db(fields=profile_updates)

        return instance

    def to_representation(self, instance):
        """Augment the serialized representation with agent info when relevant."""
        data = UserSerializer(instance, context=self.context).data
        if instance.account_type == User.AccountType.AGENT:
            agent_profile = (
                AgentProfile.objects.filter(user=instance)
                .only("id", "display_name", "is_self_represented")
                .first()
            )
            if agent_profile is not None:
                data["agent_profile"] = {
                    "id": str(agent_profile.id),
                    "display_name": agent_profile.display_name,
                    "is_self_represented": agent_profile.is_self_represented,
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
                "is_self_represented": agent_profile.is_self_represented,
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


class EmailVerificationConfirmSerializer(serializers.Serializer):
    """Validate and persist email verification submissions."""

    uid = serializers.UUIDField()
    token = serializers.CharField()

    default_error_messages = {
        "invalid_token": "Invalid or expired verification token.",
    }

    def validate(self, attrs):
        try:
            user = User.objects.get(id=attrs["uid"])
        except User.DoesNotExist as exc:  # pragma: no cover - defensive
            raise serializers.ValidationError(
                self.error_messages["invalid_token"]
            ) from exc

        token = EmailVerificationToken.verify(user, attrs["token"])
        if token is None:
            raise serializers.ValidationError(self.error_messages["invalid_token"])

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user: User = self.validated_data["user"]
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified", "updated_at"])
        return user
