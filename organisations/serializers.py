"""Serializers used across organisation endpoints."""

# pylint: disable=missing-class-docstring,too-few-public-methods

from django.db import transaction
from rest_framework import serializers

from users.models import User

from .models import Collaborator, Organisation


class OrganisationSerializer(serializers.ModelSerializer):
    """Expose organisation data including the cached owner identifier."""

    owner_id = serializers.UUIDField(source="get_owner_id", read_only=True)

    class Meta:
        model = Organisation
        fields = (
            "id",
            "name",
            "sector",
            "size",
            "budget_min",
            "budget_max",
            "logo",
            "country",
            "description",
            "website",
            "created_at",
            "updated_at",
            "owner_id",
        )
        read_only_fields = ("id", "created_at", "updated_at", "owner_id")


class OrganisationListFilter(serializers.Serializer):
    """Validate filters accepted by the organisation listing endpoint."""

    sector = serializers.CharField(required=False)
    size = serializers.ChoiceField(required=False, choices=Organisation.Size.choices)
    country = serializers.CharField(required=False)

    def create(self, validated_data):  # pylint: disable=unused-argument
        """Disallow creation on pure validation serializers."""
        raise NotImplementedError("OrganisationListFilter does not create instances.")

    def update(self, instance, validated_data):  # pylint: disable=unused-argument
        """Disallow updates on pure validation serializers."""
        raise NotImplementedError("OrganisationListFilter does not update instances.")


class OrganisationCreateSerializer(serializers.ModelSerializer):
    """Handle organisation creation and owner assignment."""

    class Meta:
        model = Organisation
        fields = (
            "name",
            "sector",
            "size",
            "budget_min",
            "budget_max",
            "logo",
            "country",
            "description",
            "website",
        )

    @transaction.atomic
    def create(self, validated_data):
        """Create the organisation and ensure the requester becomes the owner."""
        user = self.context["request"].user
        organisation = Organisation.objects.create(  # pylint: disable=no-member
            owner=user,
            **validated_data,
        )
        Collaborator.objects.create(  # pylint: disable=no-member
            user=user,
            organisation=organisation,
            role=Collaborator.Role.OWNER,
            job_title="Owner",
        )
        user.account_type = User.AccountType.COLLABORATOR
        user.save(update_fields=["account_type"])
        return organisation


class CollaboratorSerializer(serializers.ModelSerializer):
    """Represent collaborator records, exposing related user details."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = Collaborator
        fields = (
            "id",
            "user",
            "user_email",
            "user_full_name",
            "role",
            "job_title",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "user_email",
            "user_full_name",
        )

    def get_user_full_name(self, obj):
        """Return a best-effort full name for the collaborator user."""
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full_name or obj.user.email


class CollaboratorCreateSerializer(serializers.ModelSerializer):
    """Invite existing users to join an organisation as collaborators."""

    email = serializers.EmailField(write_only=True)

    class Meta:
        model = Collaborator
        fields = ("email", "role", "job_title")

    def validate_role(self, value):
        """Block invitations that attempt to assign the owner role."""
        if value == Collaborator.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot assign additional owners via invitation."
            )
        return value

    def validate(self, attrs):
        """Ensure the invitee is not already collaborating with the organisation."""
        email = attrs["email"]
        organisation = self.context["organisation"]
        if Collaborator.objects.filter(  # pylint: disable=no-member
            organisation=organisation,
            user__email=email,
        ).exists():
            raise serializers.ValidationError(
                {"email": "User is already a collaborator for this organisation."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create the collaborator entry for an existing user."""
        email = validated_data.pop("email")
        organisation = self.context["organisation"]

        try:
            user = User.objects.get(email=email)  # pylint: disable=no-member
        except User.DoesNotExist as exc:  # pylint: disable=no-member
            raise serializers.ValidationError(
                {"email": "No user found with this email address."}
            ) from exc

        collaborator = Collaborator.objects.create(  # pylint: disable=no-member
            user=user,
            organisation=organisation,
            **validated_data,
        )
        return collaborator
