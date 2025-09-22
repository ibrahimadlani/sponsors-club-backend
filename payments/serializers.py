"""Serializers for payment plans and subscriptions."""

# The serializers co-ordinate validation logic shared between the REST API and
# webhook flows. Inline comments explain why certain permission checks exist and
# how the Stripe data is normalised for Django models.

from datetime import timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import collaborator_meets_requirement, requirement_denied_payload

from .constants import PLAN_CORE_FIELDS
from .models import Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Expose subscription plan attributes to API consumers."""

    class Meta:
        """Serializer configuration for :class:`SubscriptionPlanSerializer`."""

        model = SubscriptionPlan
        fields = (
            "id",
            *PLAN_CORE_FIELDS,
            "features",
            "stripe_product_id",
            "stripe_price_id",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serialize subscription records with scoped participants."""

    organisation = serializers.PrimaryKeyRelatedField(read_only=True)
    agent = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        """Serializer configuration for :class:`SubscriptionSerializer`."""

        model = Subscription
        fields = (
            "id",
            "organisation",
            "agent",
            "plan",
            "status",
            "start_at",
            "current_period_end",
            "stripe_customer_id",
            "stripe_subscription_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SubscriptionCreateSerializer(serializers.Serializer):
    """Validate payloads that create subscription records.

    The serializer is intentionally separate from the REST view logic so that it
    can be reused by the checkout session serializer below. This keeps scope
    validation in one place for both manual and automated subscription creation
    paths.
    """

    plan_id = serializers.UUIDField()
    organisation_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    stripe_customer_id = serializers.CharField(required=False, allow_blank=True)
    stripe_subscription_id = serializers.CharField(required=False, allow_blank=True)

    def _get_plan(self, plan_id):
        """Resolve an active plan for the provided identifier.

        Args:
            plan_id (UUID): Identifier submitted by the client.

        Returns:
            SubscriptionPlan: Active plan referenced by the payload.

        Raises:
            serializers.ValidationError: If the plan cannot be found or is
                inactive.
        """

        plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
        if plan is None:
            raise serializers.ValidationError(
                {"plan_id": "Plan not found or inactive."}
            )
        return plan

    def _validate_organisation_scope(self, organisation_id, user):
        """Ensure the requesting user can manage the organisation's plan.

        Args:
            organisation_id (UUID): Organisation targeted for the subscription.
            user (User): Authenticated user submitting the request.

        Returns:
            Organisation: Organisation instance when validation succeeds.

        Raises:
            serializers.ValidationError: If the organisation does not exist, the
                user lacks ownership, or an active subscription already exists.
            PermissionDenied: If the user's feature entitlements do not allow
                subscription management.
        """

        organisation = Organisation.objects.filter(id=organisation_id).first()
        if organisation is None:
            raise serializers.ValidationError(
                {"organisation_id": "Organisation not found."}
            )

        collaborator = Collaborator.objects.filter(
            organisation=organisation,
            user=user,
        ).first()
        if not collaborator or collaborator.role != Collaborator.Role.OWNER:
            raise serializers.ValidationError(
                "Only organisation owners can manage subscriptions."
            )

        requirement = COLLABORATOR_FEATURES["organisation_subscription_management"]
        if not collaborator_meets_requirement(user, requirement):
            payload = requirement_denied_payload(
                requirement,
                "Upgrade required to manage organisation subscriptions.",
            )
            raise PermissionDenied(payload)

        has_active = (
            Subscription.objects.filter(organisation=organisation)
            .exclude(
                status=Subscription.Status.CANCELED,
            )
            .exists()
        )
        if has_active:
            raise serializers.ValidationError(
                "Organisation already has an active subscription."
            )
        return organisation

    def _validate_agent_scope(self, agent_id, user):
        """Ensure the agent profile is valid and managed by the user.

        Args:
            agent_id (UUID): Agent profile identifier to subscribe.
            user (User): Authenticated requester.

        Returns:
            AgentProfile: Agent profile when validation passes.

        Raises:
            serializers.ValidationError: If the agent cannot be found, the user
                is attempting to manage someone else's profile, or an active
                subscription already exists.
        """

        agent_profile = (
            AgentProfile.objects.filter(id=agent_id).select_related("user").first()
        )
        if agent_profile is None:
            raise serializers.ValidationError({"agent_id": "Agent not found."})
        if agent_profile.user_id != user.id and not user.is_staff:
            raise serializers.ValidationError(
                "You can only subscribe for your own agent profile."
            )

        has_active = (
            Subscription.objects.filter(agent=agent_profile)
            .exclude(
                status=Subscription.Status.CANCELED,
            )
            .exists()
        )
        if has_active:
            raise serializers.ValidationError(
                "Agent already has an active subscription."
            )
        return agent_profile

    def validate(self, attrs):
        """Ensure provided identifiers are valid and consistent.

        Args:
            attrs (dict): Raw attributes provided to the serializer.

        Returns:
            dict: Attributes augmented with resolved model instances.

        Raises:
            serializers.ValidationError: If mutually exclusive fields are used
                incorrectly or scope validation fails.
        """

        request = self.context["request"]
        user = request.user

        plan = self._get_plan(attrs["plan_id"])

        organisation_id = attrs.get("organisation_id")
        agent_id = attrs.get("agent_id")

        if organisation_id and agent_id:
            raise serializers.ValidationError(
                "Provide either organisation_id or agent_id, not both."
            )
        if not organisation_id and not agent_id:
            raise serializers.ValidationError(
                "An organisation_id or agent_id is required."
            )

        organisation = None
        agent_profile = None

        if organisation_id:
            organisation = self._validate_organisation_scope(organisation_id, user)
        else:
            agent_profile = self._validate_agent_scope(agent_id, user)

        attrs["plan"] = plan
        attrs["organisation"] = organisation
        attrs["agent_profile"] = agent_profile
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create the subscription record using validated scope.

        Args:
            validated_data (dict): Cleaned values returned from :meth:`validate`.

        Returns:
            Subscription: Newly created subscription record.
        """

        plan = validated_data["plan"]
        organisation = validated_data.get("organisation")
        agent_profile = validated_data.get("agent_profile")
        stripe_customer_id = validated_data.get("stripe_customer_id", "")
        stripe_subscription_id = validated_data.get("stripe_subscription_id", "")

        # Stripe posts timestamps separately; we accept the raw strings so the
        # serializer can be reused for both API submissions and webhooks.
        request_data = self.context["request"].data
        start_at_raw = request_data.get("start_at") or request_data.get(
            "current_period_start"
        )
        current_period_end_raw = request_data.get("current_period_end")

        start_at = parse_datetime(start_at_raw) if start_at_raw else None
        if start_at and start_at.tzinfo is None:
            start_at = timezone.make_aware(start_at, datetime_timezone.utc)

        current_period_end = (
            parse_datetime(current_period_end_raw) if current_period_end_raw else None
        )
        if current_period_end and current_period_end.tzinfo is None:
            current_period_end = timezone.make_aware(
                current_period_end, datetime_timezone.utc
            )

        subscription = Subscription.objects.create(
            organisation=organisation,
            agent=agent_profile,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            start_at=start_at or timezone.now(),
            current_period_end=current_period_end or timezone.now(),
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        return subscription

    def update(self, instance, validated_data):
        """Prevent updates through this serializer.

        Args:
            instance (Subscription): Existing subscription instance.
            validated_data (dict): Incoming data attempting to modify the record.

        Raises:
            NotImplementedError: Always raised because updates are not supported.
        """

        raise NotImplementedError("Subscription updates are not supported.")


class StripeCheckoutSessionSerializer(serializers.Serializer):
    """Validate payload for initiating a Stripe Checkout session.

    This serializer wraps :class:`SubscriptionCreateSerializer` to share the same
    permission and plan validation while adding URL fields specific to the
    checkout flow.
    """

    plan_id = serializers.UUIDField()
    organisation_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()

    def validate(self, attrs):
        """Reuse subscription validation to resolve plan and scope.

        Args:
            attrs (dict): Incoming payload for checkout session creation.

        Returns:
            dict: Attributes enriched with resolved plan and scope objects.
        """

        subscription_serializer = SubscriptionCreateSerializer(
            data={
                "plan_id": attrs["plan_id"],
                "organisation_id": attrs.get("organisation_id"),
                "agent_id": attrs.get("agent_id"),
            },
            context=self.context,
        )
        subscription_serializer.is_valid(raise_exception=True)

        validated = subscription_serializer.validated_data
        attrs["plan"] = validated["plan"]
        attrs["organisation"] = validated.get("organisation")
        attrs["agent_profile"] = validated.get("agent_profile")
        return attrs
