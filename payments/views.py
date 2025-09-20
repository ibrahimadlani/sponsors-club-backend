"""Views powering the payments API."""

import logging
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Dict, Optional

import stripe
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from stripe.error import SignatureVerificationError, StripeError

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile

from core.feature_matrix import AGENT_FEATURES, COLLABORATOR_FEATURES
from core.permissions import (
    agent_meets_requirement,
    collaborator_meets_requirement,
    requirement_denied_payload,
)

from .models import Subscription, SubscriptionPlan
from .serializers import (
    StripeCheckoutSessionSerializer,
    SubscriptionCreateSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
)

logger = logging.getLogger(__name__)


stripe.api_key = settings.STRIPE_SECRET_KEY
if getattr(settings, "STRIPE_API_VERSION", None):
    stripe.api_version = settings.STRIPE_API_VERSION
stripe.max_network_retries = 2


class StripePlanConfigurationError(Exception):
    """Raised when a subscription plan lacks Stripe configuration."""


def ensure_plan_price_id(plan: SubscriptionPlan) -> str:
    """Ensure the plan is associated with an active Stripe price."""

    if plan.stripe_price_id:
        return plan.stripe_price_id
    if not plan.stripe_product_id:
        raise StripePlanConfigurationError(
            "Plan is not configured with a Stripe product identifier."
        )

    try:
        prices = stripe.Price.list(
            product=plan.stripe_product_id,
            active=True,
            type="recurring",
            limit=1,
        )
    except StripeError as exc:  # pragma: no cover - defensive logging path
        raise StripePlanConfigurationError(
            "Unable to fetch price information from Stripe."
        ) from exc

    price_data = getattr(prices, "data", None) or []
    if not price_data:
        raise StripePlanConfigurationError(
            "No active recurring price configured on Stripe for this plan."
        )

    price_obj = price_data[0]
    price_id = getattr(price_obj, "id", None) or (
        price_obj.get("id") if isinstance(price_obj, dict) else None
    )
    if not price_id:
        raise StripePlanConfigurationError(
            "Unable to determine the Stripe price identifier for this plan."
        )

    plan.stripe_price_id = price_id
    plan.save(update_fields=["stripe_price_id", "updated_at"])
    return price_id


def timestamp_to_datetime(timestamp: Optional[Any]) -> Optional[datetime]:
    """Convert a Stripe timestamp to an aware datetime."""

    if timestamp in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=datetime_timezone.utc)
    except (TypeError, ValueError, OSError):  # pragma: no cover - invalid payload guard
        return None


def to_plain_dict(payload: Any) -> Dict[str, Any]:
    """Convert Stripe objects to dictionaries for easier handling."""

    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    return {}


def resolve_subscription_plan(
    data_object: Dict[str, Any], metadata: Dict[str, Any]
) -> Optional[SubscriptionPlan]:
    """Resolve the subscription plan matching the Stripe payload."""

    plan_id = metadata.get("plan_id")
    if plan_id:
        plan = SubscriptionPlan.objects.filter(id=plan_id).first()
        if plan:
            return plan

    price_id = None
    items = data_object.get("items") or {}
    items_data = items.get("data") if isinstance(items, dict) else getattr(items, "data", [])
    if items_data:
        first_item = items_data[0]
        price = (
            first_item.get("price")
            if isinstance(first_item, dict)
            else getattr(first_item, "price", None)
        )
        price_id = (
            price.get("id")
            if isinstance(price, dict)
            else getattr(price, "id", None)
        )

    if price_id:
        return SubscriptionPlan.objects.filter(stripe_price_id=price_id).first()
    return None


def sync_subscription_from_payload(
    data_object: Dict[str, Any],
    fallback_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Subscription]:
    """Create or update a subscription from Stripe webhook data."""

    metadata = data_object.get("metadata") or fallback_metadata or {}
    subscription_id = data_object.get("id")
    if not subscription_id:
        logger.warning("Stripe webhook missing subscription id: %s", data_object)
        return None

    plan = resolve_subscription_plan(data_object, metadata)
    if not plan:
        logger.warning(
            "Stripe subscription %s does not match a configured plan.",
            subscription_id,
        )
        return None

    scope = metadata.get("scope")
    scope_id = metadata.get("scope_id")
    organisation: Optional[Organisation] = None
    agent_profile: Optional[AgentProfile] = None

    if scope == "organisation" and scope_id:
        organisation = Organisation.objects.filter(id=scope_id).first()
    elif scope == "agent" and scope_id:
        agent_profile = AgentProfile.objects.filter(id=scope_id).first()

    subscription = Subscription.objects.filter(
        stripe_subscription_id=subscription_id
    ).first()

    status_value = data_object.get("status")
    if status_value not in dict(Subscription.Status.choices):
        status_value = Subscription.Status.INCOMPLETE

    start_at = timestamp_to_datetime(data_object.get("current_period_start"))
    current_period_end = timestamp_to_datetime(data_object.get("current_period_end"))

    if subscription is None:
        if not organisation and not agent_profile:
            logger.warning(
                "Unable to determine scope for new Stripe subscription %s.",
                subscription_id,
            )
            return None

        subscription = Subscription.objects.create(
            organisation=organisation,
            agent=agent_profile,
            plan=plan,
            status=status_value,
            start_at=start_at or timezone.now(),
            current_period_end=current_period_end or timezone.now(),
            stripe_customer_id=data_object.get("customer", ""),
            stripe_subscription_id=subscription_id,
        )
        return subscription

    update_fields = []

    if organisation and subscription.organisation_id != getattr(organisation, "id", None):
        subscription.organisation = organisation
        subscription.agent = None
        update_fields.extend(["organisation", "agent"])
    if agent_profile and subscription.agent_id != getattr(agent_profile, "id", None):
        subscription.agent = agent_profile
        subscription.organisation = None
        update_fields.extend(["agent", "organisation"])
    if subscription.plan_id != plan.id:
        subscription.plan = plan
        update_fields.append("plan")
    if subscription.status != status_value:
        subscription.status = status_value
        update_fields.append("status")

    if start_at and subscription.start_at != start_at:
        subscription.start_at = start_at
        update_fields.append("start_at")
    if current_period_end and subscription.current_period_end != current_period_end:
        subscription.current_period_end = current_period_end
        update_fields.append("current_period_end")

    stripe_customer_id = data_object.get("customer", "")
    if stripe_customer_id and subscription.stripe_customer_id != stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id
        update_fields.append("stripe_customer_id")

    if update_fields:
        subscription.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
    return subscription

class PlanListView(APIView):
    """List active subscription plans."""

    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):
        """Return all active plans ordered by price."""

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price")
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)


class StripeCheckoutSessionView(APIView):
    """Initiate a Stripe Checkout session for a subscription plan."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """Create a Stripe Checkout session tied to the requested plan."""

        del args, kwargs

        serializer = StripeCheckoutSessionSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        plan: SubscriptionPlan = serializer.validated_data["plan"]
        organisation = serializer.validated_data.get("organisation")
        agent_profile = serializer.validated_data.get("agent_profile")
        success_url: str = serializer.validated_data["success_url"]
        cancel_url: str = serializer.validated_data["cancel_url"]

        try:
            price_id = ensure_plan_price_id(plan)
        except StripePlanConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        metadata: Dict[str, str] = {
            "plan_id": str(plan.id),
            "plan_code": plan.code,
            "user_id": str(request.user.id),
        }

        if organisation:
            metadata["scope"] = "organisation"
            metadata["scope_id"] = str(organisation.id)
        elif agent_profile:
            metadata["scope"] = "agent"
            metadata["scope_id"] = str(agent_profile.id)

        if request.user.email:
            metadata["user_email"] = request.user.email

        session_payload: Dict[str, Any] = {
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
            "allow_promotion_codes": True,
            "client_reference_id": str(request.user.id),
        }

        if request.user.email:
            session_payload["customer_email"] = request.user.email

        try:
            session = stripe.checkout.Session.create(**session_payload)
        except StripeError as exc:  # pragma: no cover - network failures
            logger.exception(
                "Failed to create Stripe checkout session for plan %s", plan.code
            )
            return Response(
                {"detail": "Unable to create Stripe Checkout session."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_payload = {
            "id": session.get("id") if isinstance(session, dict) else getattr(session, "id", None),
            "url": session.get("url") if isinstance(session, dict) else getattr(session, "url", None),
            "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
            "plan": SubscriptionPlanSerializer(plan).data,
        }
        return Response(response_payload, status=status.HTTP_200_OK)


class SubscriptionCreateView(APIView):
    """Create a subscription for the requesting user."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """Validate payload and create a subscription."""

        del args, kwargs

        serializer = SubscriptionCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        subscription = serializer.save()
        return Response(
            SubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )


class MySubscriptionView(APIView):
    """Retrieve or cancel the authenticated user's subscription."""

    permission_classes = (permissions.IsAuthenticated,)

    def get_subscription(self, request):
        """Fetch the most relevant active subscription for the user."""

        user = request.user
        active_statuses = (
            Subscription.Status.ACTIVE,
            Subscription.Status.PAST_DUE,
            Subscription.Status.INCOMPLETE,
        )

        queryset = Subscription.objects.filter(status__in=active_statuses)

        try:
            agent_profile = user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
            agent_profile = None

        if agent_profile:
            agent_subscription = (
                queryset.filter(agent=agent_profile).order_by("-created_at").first()
            )
            if agent_subscription:
                return agent_subscription

        organisation_ids = list(
            Collaborator.objects.filter(user=user).values_list(
                "organisation_id", flat=True
            )
        )
        if organisation_ids:
            org_subscription = (
                queryset.filter(organisation_id__in=organisation_ids)
                .order_by("-created_at")
                .first()
            )
            if org_subscription:
                return org_subscription
        return None

    def get(self, request, *args, **kwargs):
        """Return the user's subscription details."""

        del args, kwargs

        subscription = self.get_subscription(request)
        if subscription is None:
            return Response(
                {"detail": "No active subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SubscriptionSerializer(subscription).data)

    def delete(self, request, *args, **kwargs):
        """Cancel the user's subscription when permitted."""

        del args, kwargs

        subscription = self.get_subscription(request)
        if subscription is None:
            return Response(
                {"detail": "No active subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if subscription.agent_id:
            requirement = AGENT_FEATURES["subscription_management"]
            if not agent_meets_requirement(request.user, requirement):
                payload = requirement_denied_payload(
                    requirement,
                    "Upgrade required to manage your agent subscription.",
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)
        elif subscription.organisation_id:
            requirement = COLLABORATOR_FEATURES["organisation_subscription_management"]
            if not collaborator_meets_requirement(request.user, requirement):
                payload = requirement_denied_payload(
                    requirement,
                    "Upgrade required to manage organisation subscriptions.",
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)

        subscription.status = Subscription.Status.CANCELED
        subscription.current_period_end = timezone.now()
        subscription.save(update_fields=["status", "current_period_end", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class StripeWebhookView(APIView):
    """Ingest Stripe webhook events and sync subscription state."""

    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        """Process the Stripe webhook payload."""

        del args, kwargs

        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        if webhook_secret:
            try:
                event = stripe.Webhook.construct_event(
                    payload=request.body,
                    sig_header=signature,
                    secret=webhook_secret,
                )
            except ValueError:
                logger.warning("Received invalid JSON payload from Stripe webhook.")
                return Response(
                    {"detail": "Invalid payload."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except SignatureVerificationError:
                logger.warning("Stripe webhook signature verification failed.")
                return Response(
                    {"detail": "Invalid signature."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            event = request.data

        event_dict = to_plain_dict(event)
        event_type = event_dict.get("type")
        data_object = to_plain_dict(event_dict.get("data", {})).get("object", {})
        data_object = to_plain_dict(data_object)

        if not event_type:
            logger.warning("Stripe webhook missing event type: %s", event_dict)
            return Response(
                {"detail": "Event type missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if event_type == "checkout.session.completed":
            subscription_id = data_object.get("subscription")
            metadata = data_object.get("metadata") or {}
            if not subscription_id:
                logger.info(
                    "Checkout session completed without subscription id: %s",
                    data_object,
                )
            else:
                try:
                    subscription_object = stripe.Subscription.retrieve(subscription_id)
                except StripeError as exc:  # pragma: no cover - network failures
                    logger.exception(
                        "Failed to retrieve Stripe subscription %s", subscription_id
                    )
                    return Response(
                        {"detail": "Unable to retrieve subscription."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                subscription_payload = to_plain_dict(subscription_object)
                sync_subscription_from_payload(subscription_payload, metadata)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            if not data_object:
                logger.warning("Subscription event received without data: %s", event_dict)
                return Response(
                    {"detail": "Subscription data missing."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sync_subscription_from_payload(data_object)
        else:
            logger.info("Received unhandled Stripe event %s", event_type)

        return Response({"detail": "Processed."}, status=status.HTTP_200_OK)
