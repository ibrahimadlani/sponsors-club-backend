"""Database models for subscription plans and entitlements."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from organisations.models import Organisation
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    # pylint: disable=too-few-public-methods

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django metadata for the abstract base class."""

        abstract = True


class SubscriptionPlan(BaseModel):
    """Commercial plan offered to organisations or agents."""

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    max_athletes = models.PositiveIntegerField(default=0)
    max_collaborators = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=dict, blank=True)
    stripe_product_id = models.CharField(max_length=255, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Subscription(BaseModel):
    """Active subscription instance for an organisation or agent."""

    class Status(models.TextChoices):
        """Enumeration of subscription lifecycle states."""

        # pylint: disable=too-few-public-methods

        ACTIVE = 'active', 'Active'
        PAST_DUE = 'past_due', 'Past Due'
        CANCELED = 'canceled', 'Canceled'
        INCOMPLETE = 'incomplete', 'Incomplete'

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        blank=True,
        null=True,
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        blank=True,
        null=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    start_at = models.DateTimeField()
    current_period_end = models.DateTimeField()
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)

    class Meta:
        """Django metadata for subscription model configuration."""

        # pylint: disable=too-few-public-methods

        indexes = [
            models.Index(fields=('organisation',), name='subscription_organisation_idx'),
            models.Index(fields=('agent',), name='subscription_agent_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(organisation__isnull=False, agent__isnull=True)
                    | Q(organisation__isnull=True, agent__isnull=False)
                ),
                name='subscription_scope_xor',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.organisation) == bool(self.agent):
            raise ValidationError(
                'Subscription must be scoped to either an organisation or an agent, not both.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = self.organisation or self.agent
        plan_code = getattr(self.plan, 'code', '')
        return f"Subscription for {scope} ({plan_code})"
