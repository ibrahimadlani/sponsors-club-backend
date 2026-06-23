"""Serializers used across organisation endpoints."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from users.models import User

from .models import Collaborator, Organisation, OrganisationInvite


class OrganisationSerializer(serializers.ModelSerializer):
    """Expose organisation data with robust owner identifier.

    Prefer direct FK owner when present; otherwise fall back to collaborator owner id.
    """

    # Now owner_id exposes the collaborator id; also include owner_user_id for convenience
    owner_id = serializers.SerializerMethodField()
    owner_user_id = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = (
            "id",
            "name",
            "slug",
            "type",
            "industry",
            "logo",
            "banner_image",
            "description",
            "website_url",
            "email_contact",
            "phone_contact",
            "address_city",
            "address_country",
            "address_postal_code",
            "social_links",
            "founded_year",
            "employees_count",
            "budget_range",
            "sponsoring_focus",
            "created_at",
            "updated_at",
            "owner_id",
            "owner_user_id",
        )
        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
            "owner_id",
            "owner_user_id",
        )

    def get_owner_id(self, obj: Organisation):
        # Return collaborator id (current FK) or fallback discovery
        collab_id = obj.owner_id or obj.get_owner_id()
        return str(collab_id) if collab_id else None

    def get_owner_user_id(self, obj: Organisation):
        user = obj.owner_user
        return str(user.id) if user else None


class OrganisationListFilter(serializers.Serializer):
    """Validate filters accepted by the organisation listing endpoint."""

    type = serializers.ChoiceField(required=False, choices=Organisation.Type.choices)
    industry = serializers.CharField(required=False)
    address_country = serializers.CharField(required=False)

    def create(self, validated_data):
        """Disallow creation on pure validation serializers."""
        raise NotImplementedError("OrganisationListFilter does not create instances.")

    def update(self, instance, validated_data):
        """Disallow updates on pure validation serializers."""
        raise NotImplementedError("OrganisationListFilter does not update instances.")


class OrganisationCreateSerializer(serializers.ModelSerializer):
    """Handle organisation creation and owner assignment."""

    class Meta:
        model = Organisation
        fields = (
            "name",
            "type",
            "industry",
            "logo",
            "banner_image",
            "description",
            "website_url",
            "email_contact",
            "phone_contact",
            "address_city",
            "address_country",
            "address_postal_code",
            "social_links",
            "founded_year",
            "employees_count",
            "budget_range",
            "sponsoring_focus",
        )

    @transaction.atomic
    def create(self, validated_data):
        """Create the organisation and ensure the requester becomes the owner."""
        user = self.context["request"].user
        if (
            getattr(user, "account_type", None) != User.AccountType.COLLABORATOR
            and not user.is_staff
        ):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Only collaborator accounts may create organisations."
                    ]
                }
            )
        if not user.is_staff and Collaborator.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                {"non_field_errors": ["User already belongs to an organisation."]}
            )
        organisation = Organisation.objects.create(
            **validated_data,
        )
        # Create owner collaborator then link as owner FK
        owner_collab = Collaborator.objects.create(
            user=user,
            organisation=organisation,
            role=Collaborator.Role.OWNER,
            job_title="Owner",
        )
        organisation.owner = owner_collab
        organisation.save(update_fields=["owner", "updated_at"])
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
        if Collaborator.objects.filter(
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
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"email": "No user found with this email address."}
            ) from exc

        if (
            getattr(user, "account_type", None) != User.AccountType.COLLABORATOR
            and not user.is_staff
        ):
            raise serializers.ValidationError(
                {"email": "Only collaborator accounts may join organisations."}
            )

        collaborator = Collaborator.objects.create(
            user=user,
            organisation=organisation,
            **validated_data,
        )
        return collaborator


class OrganisationInviteSerializer(serializers.ModelSerializer):
    """Expose invitation metadata for organisation owners."""

    created_by = serializers.CharField(source="created_by.user.email", read_only=True)
    status = serializers.ReadOnlyField()

    class Meta:
        model = OrganisationInvite
        fields = (
            "id",
            "code",
            "target_email",
            "expires_at",
            "is_used",
            "used_at",
            "created_at",
            "created_by",
            "status",
        )
        read_only_fields = fields


class OrganisationInviteCreateSerializer(serializers.Serializer):
    """Generate a one-time invitation code for an organisation."""

    expires_in_hours = serializers.IntegerField(
        min_value=1, max_value=168, required=False
    )
    target_email = serializers.EmailField(
        required=False,
        allow_null=True,
        help_text="Optional email of the intended recipient; "
        "triggers an automatic invitation email when provided.",
    )

    def create(self, validated_data):
        organisation: Organisation = self.context["organisation"]
        created_by: Collaborator = self.context["creator"]
        hours = validated_data.get(
            "expires_in_hours", OrganisationInvite.DEFAULT_EXPIRY_HOURS
        )
        expires_at = timezone.now() + timedelta(hours=hours)
        target_email: str | None = validated_data.get("target_email")

        code = OrganisationInvite.generate_code()
        while OrganisationInvite.objects.filter(code=code).exists():
            code = OrganisationInvite.generate_code()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=created_by,
            code=code,
            target_email=target_email,
            expires_at=expires_at,
        )
        return invite


class OrganisationJoinSerializer(serializers.Serializer):
    """Validate the payload required to join an organisation via invite code."""

    code = serializers.CharField()
    job_title = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        code = attrs["code"].strip().upper()
        attrs["code"] = code  # Store normalized code
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        code = validated_data["code"]
        job_title = validated_data.get("job_title") or "Member"
        user = self.context["request"].user

        # Lock the invite row to prevent race conditions
        try:
            invite = (
                OrganisationInvite.objects.select_for_update()
                .select_related("organisation")
                .get(code=code)
            )
        except OrganisationInvite.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"code": "Invalid invitation code."}
            ) from exc

        # Validate within the transaction after locking
        if invite.is_used:
            raise serializers.ValidationError(
                {"code": "Invitation has already been used."}
            )
        if invite.expires_at < timezone.now():
            raise serializers.ValidationError({"code": "Invitation has expired."})

        # Validate user account type
        if (
            getattr(user, "account_type", None) != user.AccountType.COLLABORATOR
            and not user.is_staff
        ):
            raise serializers.ValidationError(
                {"code": "Only collaborator accounts may join organisations."}
            )

        # Check if user already belongs to an organisation
        if Collaborator.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                {"code": "User already belongs to an organisation."}
            )

        # Create collaborator and mark invite as used
        collaborator = Collaborator.objects.create(
            user=user,
            organisation=invite.organisation,
            role=Collaborator.Role.MEMBER,
            job_title=job_title,
        )
        invite.mark_used(user)

        # Audit log + owner notification (soft failures — never block the join)
        from .services import log_invitation_action, send_invitation_accepted_email
        from .models import InvitationAuditLog

        request = self.context.get("request")
        log_invitation_action(
            invite,
            InvitationAuditLog.Action.ACCEPTED,
            request=request,
        )
        send_invitation_accepted_email(invite, user.email)

        return collaborator


class CollaboratorJobTitleSerializer(serializers.Serializer):
    """Update payload used when editing a collaborator job title."""

    job_title = serializers.CharField(max_length=255)


class OwnershipTransferSerializer(serializers.Serializer):
    """Validate requests to transfer organisation ownership."""

    collaborator_id = serializers.UUIDField()

    def validate(self, attrs):
        organisation: Organisation = self.context["organisation"]
        collaborator_id = attrs["collaborator_id"]
        try:
            collaborator = organisation.collaborators.get(id=collaborator_id)
        except Collaborator.DoesNotExist as exc:
            raise serializers.ValidationError(
                {
                    "collaborator_id": "Collaborator does not belong to this organisation."
                }
            ) from exc
        if collaborator.role == Collaborator.Role.OWNER:
            raise serializers.ValidationError(
                {"collaborator_id": "Collaborator is already the owner."}
            )
        attrs["collaborator"] = collaborator
        return attrs
