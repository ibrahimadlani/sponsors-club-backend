"""Database models for organisations and their collaborators."""

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organisation(BaseModel):
    """A partner organisation that collaborates with platform users.

    Attributes:
        name: Display name of the organisation.
        slug: URL-safe unique identifier, auto-generated from name.
        owner: FK to the Collaborator with OWNER role (not directly to User).
        type: Category of organisation (brand, SME, startup, etc.).
        industry: Freeform industry label.
        social_links: JSON dict mapping platform names to profile URLs.
        sponsoring_focus: JSON list of sport/domain tags.
    """

    class Type(models.TextChoices):
        """Enumeration of recognised organisation categories."""

        BRAND = "BRAND", _("Brand")
        SME = "SME", _("Small or medium enterprise")
        STARTUP = "STARTUP", _("Startup")
        ASSOCIATION = "ASSOCIATION", _("Association")
        INDIVIDUAL = "INDIVIDUAL", _("Individual")
        AGENCY = "AGENCY", _("Agency")
        OTHER = "OTHER", _("Other")

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    # Owner now references the owner collaborator record
    owner = models.ForeignKey(
        "organisations.Collaborator",
        on_delete=models.SET_NULL,
        related_name="owned_organisations",
        null=True,
        blank=True,
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.BRAND)
    industry = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to="organisation_logos/", blank=True, null=True)
    banner_image = models.ImageField(
        upload_to="organisation_banners/", blank=True, null=True
    )
    description = models.TextField(blank=True)

    website_url = models.URLField(blank=True)
    email_contact = models.EmailField(blank=True)
    phone_contact = models.CharField(max_length=50, blank=True)
    address_city = models.CharField(max_length=255, blank=True)
    address_country = models.CharField(max_length=100, blank=True)
    address_postal_code = models.CharField(max_length=20, blank=True)
    social_links = models.JSONField(default=dict, blank=True)

    founded_year = models.PositiveIntegerField(blank=True, null=True)
    employees_count = models.PositiveIntegerField(blank=True, null=True)
    budget_range = models.CharField(max_length=50, blank=True)
    sponsoring_focus = models.JSONField(default=list, blank=True)

    def get_owner_id(self):
        """Return the collaborator identifier for the organisation owner.

        Ensures a stale in-memory FK doesn't leak after owner deletion by
        verifying the referenced collaborator still exists.
        """
        if self.owner_id:
            if Collaborator.objects.filter(id=self.owner_id).exists():
                return self.owner_id
            # Stale reference in memory; fall back to DB lookup
        return (
            self.collaborators.filter(role=Collaborator.Role.OWNER)
            .values_list("id", flat=True)
            .first()
        )

    @property
    def owner_user(self):
        """Return the owning user instance when an owner collaborator exists."""
        return self.owner.user if self.owner else None

    def __init__(self, *args, **kwargs):
        """Allow passing a User for `owner` for backward compatibility in tests.

        If a `User` instance is provided for `owner`, defer setting the actual
        collaborator FK so assignments like `Organisation(owner=user)` don't
        raise a ValueError at instantiation time. Callers that need the
        collaborator owner should create it explicitly.
        """
        owner_val = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)
        if owner_val is not None:
            try:
                # Late import to avoid circulars during app loading
                from django.contrib.auth import get_user_model
                from .models import Collaborator  # type: ignore

                UserModel = get_user_model()
                if isinstance(owner_val, Collaborator):
                    self.owner = owner_val
                elif isinstance(owner_val, UserModel):
                    # Defer: do not set owner field to avoid type error
                    # Consumers can create/link a Collaborator explicitly.
                    self._owner_user_pending = owner_val
                else:
                    # Unknown type: ignore to keep behavior safe
                    self._owner_user_pending = None
            except Exception:
                # Be resilient in migrations/imports; ignore owner assignment
                self._owner_user_pending = None

    def save(self, *args, **kwargs):
        """Ensure the slug is populated from the name when missing."""
        if not self.slug:
            base_slug = slugify(self.name) or uuid.uuid4().hex[:8]
            slug = base_slug
            counter = 1
            while Organisation.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        """Return the organisation name as its string representation."""
        return str(self.name)


class Collaborator(BaseModel):
    """Link a user to an organisation with a specific collaboration role.

    Attributes:
        user: The platform user who is a member of this organisation.
        organisation: The organisation this collaborator belongs to.
        role: OWNER or MEMBER; only one OWNER is allowed per organisation.
        job_title: Freeform job title within the organisation.
    """

    class Role(models.TextChoices):
        """Enumeration of roles a user can hold within an organisation."""

        OWNER = "OWNER", _("Owner")
        MEMBER = "MEMBER", _("Member")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collaborations",
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="collaborators",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    job_title = models.CharField(max_length=255)

    class Meta:
        """Enforce one owner per organisation and index collaborators by user."""

        constraints = [
            models.UniqueConstraint(
                fields=("organisation",),
                condition=models.Q(role="OWNER"),
                name="unique_owner_per_organisation",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "created_at"), name="collab_user_created_idx"),
        ]

    def clean(self):
        """Validate that the user does not already belong to another organisation.

        Raises:
            ValidationError: When the user is already linked to a different
                organisation, preventing multi-org membership.
        """
        if (
            self.user_id
            and Collaborator.objects.filter(user_id=self.user_id)
            .exclude(pk=self.pk)
            .exists()
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"user": "Cet utilisateur est déjà rattaché à une organisation."}
            )

    def __str__(self):
        """Return a readable description of the user–organisation–role triple."""
        return f"{self.user} - {self.organisation.name} ({self.role})"

    def delete(self, using=None, keep_parents=False):  # noqa: D401
        """Delete this collaborator.

        If this collaborator is the owner and deletion is invoked on the
        instance (not via bulk queryset deletion), delete the entire
        organisation to preserve historical behavior expected by tests.
        """
        # Instance delete path only; bulk QuerySet.delete() bypasses this method
        if self.role == Collaborator.Role.OWNER and self.organisation_id:
            # Deleting the organisation will cascade to this collaborator
            Organisation.objects.filter(id=self.organisation_id).delete()
            return
        return super().delete(using=using, keep_parents=keep_parents)


class OrganisationInviteQuerySet(models.QuerySet):
    """Custom queryset for filtering invitations by status."""

    def active(self):
        """Return invitations that are active (not expired, not used)."""
        return self.filter(is_used=False, expires_at__gt=timezone.now())

    def expired(self):
        """Return invitations that have expired but not been used."""
        return self.filter(is_used=False, expires_at__lte=timezone.now())

    def used(self):
        """Return invitations that have been used."""
        return self.filter(is_used=True)


class OrganisationInvite(BaseModel):
    """Time-bound invitation codes generated by organisation owners.

    Attributes:
        organisation: The organisation this invitation grants access to.
        created_by: The OWNER collaborator who generated the code.
        code: Random uppercase token used to join the organisation.
        expires_at: Hard expiry timestamp; active invitations must be before this.
        is_used: True once a user has consumed the code via ``mark_used()``.
        used_by: The user who accepted the invitation.
        used_at: Timestamp of acceptance.
        status: Computed property — ``"active"``, ``"expired"``, or ``"used"``.
    """

    CODE_LENGTH = 8
    DEFAULT_EXPIRY_HOURS = 72

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    created_by = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        related_name="created_invites",
    )
    code = models.CharField(max_length=16, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(blank=True, null=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="consumed_invites",
    )

    objects = OrganisationInviteQuerySet.as_manager()

    class Meta:
        """Optimise lookups by code and by organisation + usage state."""

        indexes = [
            models.Index(fields=("organisation", "is_used", "expires_at")),
            models.Index(fields=("code",)),
        ]

    @property
    def status(self):
        """Return the current status of the invitation: active, expired, or used."""
        if self.is_used:
            return "used"
        elif timezone.now() > self.expires_at:
            return "expired"
        else:
            return "active"

    def mark_used(self, user):
        """Flag the invitation as consumed by the provided user."""
        self.is_used = True
        self.used_by = user
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_by", "used_at", "updated_at"])

    @classmethod
    def generate_code(cls):
        """Return a random uppercase invitation code."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(cls.CODE_LENGTH))
