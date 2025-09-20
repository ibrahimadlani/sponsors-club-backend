"""Core data models for the users application."""


import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _


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
            raise ValueError('Users must have an email address')

        email = self.normalize_email(email)
        account_type = extra_fields.pop('account_type', self.model.AccountType.AGENT)
        user = self.model(email=email, account_type=account_type, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and persist a superuser with elevated privileges."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('account_type', self.model.AccountType.AGENT)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Primary user model backing authentication and account metadata."""

    class AccountType(models.TextChoices):
        AGENT = 'AGENT', _('Agent')
        COLLABORATOR = 'COLLABORATOR', _('Collaborator')

    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    phone_number = models.CharField(_('phone number'), max_length=32, blank=True)
    date_of_birth = models.DateField(_('date of birth'), blank=True, null=True)
    email_verified = models.BooleanField(_('email verified'), default=False)
    password_hash = models.CharField(_('password hash'), max_length=128, blank=True)
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    account_type = models.CharField(
        _('account type'),
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.AGENT,
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        """Return the most informative representation for administrators."""
        display_name = f"{self.first_name} {self.last_name}".strip()
        return display_name or self.email

    def set_password(self, raw_password):
        """Persist the password hash on both Django and legacy fields."""
        super().set_password(raw_password)
        self.password_hash = self.password

    def save(self, *args, **kwargs):
        """Mirror Django's password hash onto the legacy password column."""
        if self.password and self.password != self.password_hash:
            self.password_hash = self.password
        super().save(*args, **kwargs)


class AgentProfile(BaseModel):
    """Profile details that extend the base user for agent accounts."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agent_profile')
    display_name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)

    def __str__(self):
        """Return the display name or fall back to the related user."""
        if self.display_name:
            return str(self.display_name)
        return str(self.user)
