"""Database models for subscription plans, entitlements, and marketplace fees.

The module covers two eras of the commercial model:
- Legacy SaaS subscriptions (SubscriptionPlan / Subscription) kept for
  billing history and backward-compatibility with existing Stripe webhooks.
- Transactional Marketplace models (AthletePaymentAccount / PlatformFee)
  that drive the new "success fee" revenue stream tied to contract signing.
"""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

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


class SubscriptionPlanManager(models.Manager):
    """Enable natural key lookups based on the immutable plan code."""

    def get_by_natural_key(self, code: str):  # type: ignore[override]
        return self.get(code=code)


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

    objects = SubscriptionPlanManager()

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

    def natural_key(self) -> tuple[str]:
        """Expose the plan code as a natural key for fixtures.

        Returns:
            tuple[str]: Single element tuple containing the unique plan code.
        """

        return (self.code,)


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


# ---------------------------------------------------------------------------
# Transactional Marketplace models
# ---------------------------------------------------------------------------


class AthletePaymentAccount(BaseModel):
    """Stripe Connect Express account for an athlete's payout routing.

    Created once the athlete completes the Stripe onboarding flow.  Until
    ``is_onboarded`` is True, the platform cannot route earnings to them.

    Attributes:
        athlete: One-to-one link to the athlete profile.
        stripe_account_id: Stripe Connect account identifier (``acct_…``).
        is_onboarded: True once the onboarding form has been completed.
        charges_enabled: Mirror of Stripe's ``charges_enabled`` flag.
        payouts_enabled: Mirror of Stripe's ``payouts_enabled`` flag.
    """

    athlete = models.OneToOneField(
        "athletes.Athlete",
        on_delete=models.CASCADE,
        related_name="payment_account",
    )
    stripe_account_id = models.CharField(max_length=255, unique=True)
    is_onboarded = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)

    def __str__(self) -> str:  # pragma: no cover
        return f"Stripe Connect: {self.athlete} ({self.stripe_account_id})"


class PlatformFee(BaseModel):
    """Invoice generated automatically when a contract reaches AGREEMENT status.

    The platform charges a success fee whose amount depends on the nature of
    the contract counterparts:
    - At least one CASH counterpart → 10 % commission on total cash value
      with a €10 minimum.
    - Non-cash counterparts only → fixed fee of €49.

    The ``status`` field acts as the paywall: DocuSign envelope creation is
    blocked until ``status == PAID``.  Payment confirmation arrives via the
    ``payment_intent.succeeded`` Stripe webhook which flips the status.

    Attributes:
        contract: The contract that triggered this fee (one-to-one).
        fee_type: Pricing rule used to compute the amount.
        amount_due: Exact amount owed in EUR, set at invoice generation.
        status: Lifecycle state tracked from PENDING through PAID.
        stripe_payment_intent_id: Stripe PaymentIntent reference for reconciliation.
        paid_at: Timestamp recorded when the Stripe webhook confirms payment.
    """

    CASH_COMMISSION_RATE: Decimal = Decimal("0.10")
    CASH_COMMISSION_MINIMUM: Decimal = Decimal("10.00")
    MATERIAL_FIXED_AMOUNT: Decimal = Decimal("49.00")

    class FeeType(models.TextChoices):
        CASH_COMMISSION = "cash_commission", "Cash commission (10 %)"
        MATERIAL_FIXED_FEE = "material_fixed_fee", "Fixed fee – material contract (€49)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"
        DISPUTED = "disputed", "Disputed"
        WAIVED = "waived", "Waived by staff"

    contract = models.OneToOneField(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="platform_fee",
    )
    fee_type = models.CharField(max_length=32, choices=FeeType.choices)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="platform_fee_status_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return (
            f"PlatformFee {self.fee_type} – €{self.amount_due}"
            f" [{self.get_status_display()}] ({self.contract_id})"
        )

    def mark_paid(self, stripe_payment_intent_id: str = "") -> None:
        """Record a successful payment and flip the status to PAID.

        Args:
            stripe_payment_intent_id: Stripe PaymentIntent reference for
                audit and reconciliation purposes.
        """
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        if stripe_payment_intent_id:
            self.stripe_payment_intent_id = stripe_payment_intent_id
        self.save(
            update_fields=[
                "status",
                "paid_at",
                "stripe_payment_intent_id",
                "updated_at",
            ]
        )
