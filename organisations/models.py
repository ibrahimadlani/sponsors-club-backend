"""Database models for organisations and their collaborators."""

# pylint: disable=missing-class-docstring,too-few-public-methods

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organisation(BaseModel):
    """A partner organisation that collaborates with platform users."""

    class Size(models.TextChoices):
        SMALL = "SMALL", _("Small")
        MEDIUM = "MEDIUM", _("Medium")
        LARGE = "LARGE", _("Large")
        ENTERPRISE = "ENTERPRISE", _("Enterprise")

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_organisations",
        null=True,
        blank=True,
    )
    sector = models.CharField(max_length=255)
    size = models.CharField(max_length=20, choices=Size.choices)
    budget_min = models.DecimalField(max_digits=12, decimal_places=2)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2)
    logo = models.ImageField(upload_to="organisation_logos/", blank=True, null=True)
    country = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)

    def get_owner_id(self):
        """Return the collaborator identifier for the organisation owner."""
        owner = self.collaborators.filter(  # pylint: disable=no-member
            role=Collaborator.Role.OWNER
        ).first()
        return owner.id if owner else None

    def __str__(self):
        return str(self.name)


class Collaborator(BaseModel):
    """Link a user to an organisation with a specific collaboration role."""

    class Role(models.TextChoices):
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
        constraints = [
            models.UniqueConstraint(
                fields=("organisation",),
                condition=models.Q(role="OWNER"),
                name="unique_owner_per_organisation",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.organisation.name} ({self.role})"
