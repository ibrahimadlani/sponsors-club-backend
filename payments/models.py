"""Database models for subscription plans and entitlements."""

# The payments models store commercial plans and the subscriptions linking them
# to organisations or agents. The inline comments explain the business rules so
# future maintainers can reason about constraints quickly.

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from organisations.models import Organisation
from users.models import AgentProfile


class BaseModel(models.Model):
    """Abstract base model with UUID primary key and audit timestamps.

    Attributes:
        id (UUIDField): Primary key generated via :func:`uuid.uuid4`.
        created_at (DateTimeField): Timestamp of initial record creation.
        updated_at (DateTimeField): Timestamp automatically updated on save.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Django metadata describing the abstract base class."""

        abstract = True


class SubscriptionPlan(BaseModel):
    """Commercial plan offered to organisations or agents.

    Attributes:
        code (CharField): Unique code used to reference the plan in Stripe.
        name (CharField): Human readable name shown in the UI and invoices.
        price (DecimalField): Monthly price charged for the plan.
        currency (CharField): ISO currency code for the amount.
        max_athletes (PositiveIntegerField): Entitlement limit for athlete count.
        max_collaborators (PositiveIntegerField): Entitlement limit for staff.
        features (JSONField): Feature toggles used across the platform.
        stripe_product_id (CharField): Cached identifier of the Stripe product.
        stripe_price_id (CharField): Cached identifier of the Stripe price.
        is_active (BooleanField): Flag to hide deprecated plans from sale.
    """

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="EUR")
    max_athletes = models.PositiveIntegerField(default=0)
    max_collaborators = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=dict, blank=True)
    stripe_product_id = models.CharField(max_length=255, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        """Return the readable representation used in admin listings.

        Returns:
            str: Combination of plan name and unique code.
        """

        return f"{self.name} ({self.code})"


class Subscription(BaseModel):
    """Active subscription instance for an organisation or agent.

    Attributes:
        organisation (ForeignKey): Organisation that holds the subscription.
        agent (ForeignKey): Agent profile that holds the subscription.
        plan (ForeignKey): Pricing plan applied to the subscription.
        status (CharField): Lifecycle state tracked by :class:`Status`.
        start_at (DateTimeField): When the subscription became effective.
        current_period_end (DateTimeField): Billing cycle end timestamp.
        stripe_customer_id (CharField): Stripe customer identifier reference.
        stripe_subscription_id (CharField): Stripe subscription identifier.
    """

    class Status(models.TextChoices):
        """Enumeration of subscription lifecycle states used for billing."""

        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        CANCELED = "canceled", "Canceled"
        INCOMPLETE = "incomplete", "Incomplete"
        TRIALING = "trialing", "Trialing"
        INCOMPLETE_EXPIRED = "incomplete_expired", "Incomplete Expired"
        UNPAID = "unpaid", "Unpaid"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        blank=True,
        null=True,
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        blank=True,
        null=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
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
        """Django metadata configuring indexes and validation constraints."""

        indexes = [
            models.Index(
                fields=("organisation",), name="subscription_organisation_idx"
            ),
            models.Index(fields=("agent",), name="subscription_agent_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(organisation__isnull=False, agent__isnull=True)
                    | Q(organisation__isnull=True, agent__isnull=False)
                ),
                name="subscription_scope_xor",
            ),
        ]

    def clean(self) -> None:
        """Validate that exactly one subscription scope has been provided.

        Raises:
            ValidationError: If both organisation and agent are set, or neither
                value is supplied when the record is saved.
        """

        super().clean()
        if bool(self.organisation) == bool(self.agent):
            raise ValidationError(
                "Subscription must be scoped to either an organisation or an agent, not both."
            )

    def save(self, *args, **kwargs) -> None:
        """Clean the instance before saving to enforce scope validation."""

        # Calling ``full_clean`` ensures ``clean`` runs on updates too so that
        # operators cannot accidentally link a subscription to both scopes.
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Return a concise description showing the scope and plan.

        Returns:
            str: Human readable description used in admin screens.
        """

        scope = self.organisation or self.agent
        plan_code = getattr(self.plan, "code", "")
        return f"Subscription for {scope} ({plan_code})"
