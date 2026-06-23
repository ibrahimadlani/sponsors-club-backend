"""Core data models for the users application."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    """Custom manager that relies on the email address as the username."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and persist a standard user account."""
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)
        account_type = extra_fields.pop("account_type", self.model.AccountType.AGENT)
        user = self.model(email=email, account_type=account_type, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and persist a superuser with elevated privileges."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("account_type", self.model.AccountType.AGENT)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Primary user model backing authentication and account metadata.

    Attributes:
        email: Unique login identifier; used as USERNAME_FIELD.
        account_type: AGENT for sports agents; COLLABORATOR for brand/org users.
        email_verified: True once the user has confirmed their email address.
        phone_country_code: ITU-T E.164 country code (e.g., "+33").
        phone_number: Local phone number; combined with country code must be unique.
        country: ISO 3166-1 alpha-2 country code (e.g., "FR").
        language: ISO 639-1 preferred language code, defaults to "fr".
        password_hash: Legacy copy of Django's hashed password, kept in sync.
    """

    class AccountType(models.TextChoices):
        """Two account types that determine the user's role on the platform."""

        AGENT = "AGENT", _("Agent")
        COLLABORATOR = "COLLABORATOR", _("Collaborator")

    class Gender(models.TextChoices):
        """Gender options available on the user's profile."""

        MALE = "MALE", _("Homme")
        FEMALE = "FEMALE", _("Femme")
        NON_BINARY = "NON_BINARY", _("Non-binaire")

    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    avatar = models.ImageField(
        _("avatar"), upload_to="user_avatars/", blank=True, null=True
    )
    phone_country_code = models.CharField(
        _("phone country code"), max_length=8, blank=True, null=True
    )
    phone_number = models.CharField(
        _("phone number"), max_length=32, blank=True, null=True
    )
    date_of_birth = models.DateField(_("date of birth"), blank=True, null=True)
    country = models.CharField(
        _("country"),
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g., FR, US, GB)",
    )
    language = models.CharField(
        _("language"),
        max_length=2,
        blank=True,
        default="fr",
        help_text="ISO 639-1 language code (e.g., fr, en, es)",
    )
    gender = models.CharField(
        _("gender"),
        max_length=20,
        choices=Gender.choices,
        blank=True,
        null=True,
    )
    email_verified = models.BooleanField(_("email verified"), default=False)
    password_hash = models.CharField(_("password hash"), max_length=128, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    account_type = models.CharField(
        _("account type"),
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.AGENT,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        """Enforce unique phone number pairs when both fields are provided."""

        constraints = [
            models.UniqueConstraint(
                fields=("phone_country_code", "phone_number"),
                condition=Q(
                    phone_country_code__isnull=False,
                    phone_number__isnull=False,
                ),
                name="unique_user_phone_cc_number",
            )
        ]

    def __str__(self):
        """Return the most informative representation for administrators."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def set_password(self, raw_password):
        """Persist the password hash on both Django and legacy fields."""
        super().set_password(raw_password)
        self.password_hash = self.password

    def save(self, *args, **kwargs):
        """Mirror Django's password hash onto the legacy password column."""
        if self.phone_country_code == "":
            self.phone_country_code = None
        if self.phone_number == "":
            self.phone_number = None
        if self.password and self.password != self.password_hash:
            self.password_hash = self.password
        super().save(*args, **kwargs)


class AgentProfile(BaseModel):
    """Profile details that extend the base user for agent accounts.

    Attributes:
        user: The platform account this profile extends (1:1).
        bio: Optional freeform biography displayed on the agent's public page.
        is_self_represented: True when the agent manages their own athlete career.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="agent_profile"
    )
    bio = models.TextField(blank=True)
    is_self_represented = models.BooleanField(default=False)

    def __str__(self):
        """Return the related user's preferred representation."""
        return str(self.user)

    @property
    def name(self) -> str:
        """Return a human-friendly representation for API consumers."""

        return str(self.user)


class RepresentativeProfile(BaseModel):
    """Generic profile for any person surrounding an athlete (entourage).

    Replaces the exclusive agent model with a flexible representation layer.
    Any user — parent, coach, club secretary, licensed agent — can hold a
    ``RepresentativeProfile`` and be granted a ``RepresentationMandate`` with
    the exact permissions that match their real-world role.

    KYC verification and federation licensing are tracked here so that sponsors
    can see a trust badge ("Verified Parent", "Licensed Agent FFF") on the
    athlete's public profile before committing to a deal.

    Attributes:
        user: The platform account attached to this representative.
        is_kyc_verified: Whether the representative has submitted and passed
            identity verification (government-issued ID check).
        license_number: Optional federation license number, populated only when
            the representative is a certified sports agent.
        licensing_federation: Name of the federation that issued the license
            (e.g., "Fédération Française de Football").
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="representative_profile",
    )
    is_kyc_verified = models.BooleanField(
        default=False,
        help_text="Representative has passed identity verification.",
    )
    license_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Federation license number — populated only for certified sports agents.",
    )
    licensing_federation = models.CharField(
        max_length=255,
        blank=True,
        help_text="Federation that issued the agent license (e.g., FFF, FFBB).",
    )

    def __str__(self) -> str:  # pragma: no cover
        return str(self.user)

    @property
    def is_licensed_agent(self) -> bool:
        """Return True when the profile carries a valid federation license number.

        Returns:
            bool: ``True`` when ``license_number`` is non-empty.
        """
        return bool(self.license_number)

    @property
    def trust_label(self) -> str:
        """Return a human-readable trust badge for display on public profiles.

        Returns:
            str: Concise label combining KYC state and agent status.
        """
        if self.is_licensed_agent and self.is_kyc_verified:
            return "Licensed Agent (Verified)"
        if self.is_licensed_agent:
            return "Licensed Agent"
        if self.is_kyc_verified:
            return "Verified Representative"
        return "Representative"


class EmailVerificationToken(BaseModel):
    """Token issued to confirm a user's email address.

    Attributes:
        user: The user who must verify their email.
        token_hash: SHA-256 digest of the raw token sent by email; never stored
            in plain text.
        expires_at: Hard expiry; tokens are invalid after this timestamp.
        used_at: Set when the token is consumed via ``verify()``; null means unused.
        TOKEN_BYTES: Entropy size used to generate raw tokens (32 bytes → 43 chars).
        EXPIRY_HOURS: Token validity window in hours (default 48).
    """

    TOKEN_BYTES = 32
    EXPIRY_HOURS = 48

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    token_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Optimise lookups by user + expiry window."""

        indexes = [
            models.Index(fields=("user", "expires_at")),
        ]

    @classmethod
    def _hash(cls, raw_token: str) -> str:
        """Return the SHA-256 hex digest of a raw token string.

        Args:
            raw_token: The plain-text token to hash.

        Returns:
            A 64-character hexadecimal SHA-256 digest.
        """
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def issue_for_user(cls, user: User) -> str:
        """Create a new verification token for the provided user."""

        raw_token = secrets.token_urlsafe(cls.TOKEN_BYTES)
        token_hash = cls._hash(raw_token)
        expires_at = timezone.now() + timedelta(hours=cls.EXPIRY_HOURS)
        cls.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now(), updated_at=timezone.now()
        )
        cls.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return raw_token

    @classmethod
    def verify(cls, user: User, raw_token: str) -> "EmailVerificationToken | None":
        """Return the token instance if valid, otherwise ``None``."""

        token_hash = cls._hash(raw_token)
        try:
            token = cls.objects.get(
                user=user,
                token_hash=token_hash,
                used_at__isnull=True,
            )
        except cls.DoesNotExist:
            return None
        if token.expires_at < timezone.now():
            return None
        token.used_at = timezone.now()
        token.save(update_fields=["used_at", "updated_at"])
        return token
