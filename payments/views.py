"""Views powering the payments API."""

# The module integrates with Stripe for subscription checkout, plan management,
# and webhook ingestion. Detailed docstrings explain each helper so the
# accounting and entitlement logic is easy to audit.

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Dict, Iterable, Optional

import stripe
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from stripe import InvalidRequestError, SignatureVerificationError, StripeError

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile

from core.feature_matrix import AGENT_FEATURES, COLLABORATOR_FEATURES
from core.permissions import (
    agent_meets_requirement,
    collaborator_meets_requirement,
    requirement_denied_payload,
)

from .models import PlatformFee, Subscription, SubscriptionPlan
from .serializers import (
    StripeCheckoutSessionSerializer,
    SubscriptionCreateSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
)

logger = logging.getLogger(__name__)


stripe.api_key = settings.STRIPE_SECRET_KEY or None
if getattr(settings, "STRIPE_API_VERSION", None):
    stripe.api_version = settings.STRIPE_API_VERSION
stripe.max_network_retries = 2


class StripePlanConfigurationError(Exception):
    """Raised when a subscription plan lacks Stripe configuration."""


class StripeConfigurationError(Exception):
    """Raised when the Stripe integration is not properly configured."""


def _require_stripe_secret_key() -> str:
    """Ensure a Stripe secret key is configured before making API calls.

    Returns:
        str: Configured Stripe secret key used for API authentication.

    Raises:
        StripeConfigurationError: If the project settings do not define a
            usable secret key.
    """

    secret_key = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    if not secret_key:
        raise StripeConfigurationError(
            "Stripe integration is not configured. Please contact support."
        )
    return secret_key


def _decimal_to_cents(amount: Decimal) -> int:
    """Convert a decimal amount to minor currency units (cents).

    Args:
        amount (Decimal): Monetary amount expressed in major currency units.

    Returns:
        int: Value converted to cents after rounding to two decimal places.
    """

    quantized = (amount or Decimal("0")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return int((quantized * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _ensure_plan_product(plan: SubscriptionPlan) -> str:
    """Ensure a Stripe product exists for the given plan.

    Args:
        plan (SubscriptionPlan): Plan whose product should be verified or
            created on Stripe.

    Returns:
        str: Identifier of the Stripe product associated with the plan.

    Raises:
        StripePlanConfigurationError: If the product cannot be retrieved or
            created due to API errors.
    """

    if plan.stripe_product_id:
        try:
            product = stripe.Product.retrieve(plan.stripe_product_id)
            product_id = getattr(product, "id", None) or (
                product.get("id") if isinstance(product, dict) else None
            )
            if product_id:
                return product_id
        except InvalidRequestError as exc:
            if getattr(exc, "code", "") != "resource_missing":
                raise StripePlanConfigurationError(
                    "Unable to verify the Stripe product for this plan."
                ) from exc
        except StripeError as exc:  # pragma: no cover - defensive logging path
            raise StripePlanConfigurationError(
                "Unable to verify the Stripe product for this plan."
            ) from exc

    try:
        product = stripe.Product.create(
            name=plan.name,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
            },
        )
    except StripeError as exc:  # pragma: no cover - defensive logging path
        raise StripePlanConfigurationError(
            "Unable to create a Stripe product for this plan."
        ) from exc

    product_id = getattr(product, "id", None) or (
        product.get("id") if isinstance(product, dict) else None
    )
    if not product_id:
        raise StripePlanConfigurationError(
            "Unable to determine the Stripe product identifier for this plan."
        )

    plan.stripe_product_id = product_id
    plan.save(update_fields=["stripe_product_id", "updated_at"])
    return product_id


def _select_matching_price(
    prices: Iterable[Any], plan: SubscriptionPlan
) -> Optional[str]:
    """Return the identifier of a price that matches the plan amount and currency.

    Args:
        prices (Iterable[Any]): Price objects or dictionaries returned by the
            Stripe API.
        plan (SubscriptionPlan): Plan whose pricing configuration we compare
            against.

    Returns:
        Optional[str]: Matching Stripe price identifier if one exists.
    """

    target_currency = (plan.currency or "").lower()
    expected_amount = _decimal_to_cents(plan.price)

    for price_obj in prices:
        price_dict = to_plain_dict(price_obj)
        currency = (
            price_dict.get("currency") or getattr(price_obj, "currency", "")
        ).lower()
        if currency != target_currency:
            continue

        amount = price_dict.get("unit_amount")
        if amount is None:
            amount = getattr(price_obj, "unit_amount", None)
        unit_amount_decimal = price_dict.get("unit_amount_decimal") or getattr(
            price_obj, "unit_amount_decimal", None
        )
        if amount is None and unit_amount_decimal is not None:
            try:
                amount = int(Decimal(str(unit_amount_decimal)))
            except (ArithmeticError, ValueError):  # pragma: no cover - invalid payload
                continue

        if amount == expected_amount:
            price_id = price_dict.get("id") or getattr(price_obj, "id", None)
            if price_id:
                return price_id
    return None


def ensure_plan_price_id(plan: SubscriptionPlan) -> str:
    """Ensure the plan is associated with an active Stripe price.

    Args:
        plan (SubscriptionPlan): Plan whose Stripe price should be confirmed.

    Returns:
        str: Identifier of the verified or newly created Stripe price.

    Raises:
        StripeConfigurationError: If Stripe credentials are missing.
        StripePlanConfigurationError: If Stripe rejects product or price
            requests.
    """

    _require_stripe_secret_key()

    if plan.stripe_price_id:
        return plan.stripe_price_id

    product_id = _ensure_plan_product(plan)

    try:
        prices = stripe.Price.list(
            product=product_id,
            active=True,
            type="recurring",
            limit=10,
        )
    except StripeError as exc:  # pragma: no cover - defensive logging path
        raise StripePlanConfigurationError(
            "Unable to fetch price information from Stripe."
        ) from exc

    price_data = getattr(prices, "data", None) or []
    price_id = _select_matching_price(price_data, plan)

    if price_id is None and price_data:
        # A recurring price exists but does not match the configured amount; fall back to
        # creating a dedicated price to ensure checkout consistency.
        logger.warning(
            "Plan %s has mismatched Stripe prices; creating a dedicated price.",
            plan.code,
        )

    if price_id is None:
        try:
            created_price = stripe.Price.create(
                product=product_id,
                currency=(plan.currency or "").lower(),
                unit_amount=_decimal_to_cents(plan.price),
                recurring={"interval": "month"},
                nickname=plan.name,
                metadata={
                    "plan_id": str(plan.id),
                    "plan_code": plan.code,
                },
            )
        except StripeError as exc:  # pragma: no cover - defensive logging path
            raise StripePlanConfigurationError(
                "Unable to create a Stripe price for this plan."
            ) from exc

        price_id = getattr(created_price, "id", None) or (
            created_price.get("id") if isinstance(created_price, dict) else None
        )

    if not price_id:
        raise StripePlanConfigurationError(
            "Unable to determine the Stripe price identifier for this plan."
        )

    plan.stripe_price_id = price_id
    plan.save(update_fields=["stripe_price_id", "updated_at"])
    return price_id


def timestamp_to_datetime(timestamp: Optional[Any]) -> Optional[datetime]:
    """Convert a Stripe timestamp to an aware datetime.

    Args:
        timestamp (Optional[Any]): Unix timestamp or timestamp string returned
            by Stripe.

    Returns:
        Optional[datetime]: Aware datetime in UTC when parsing succeeds, else
            ``None`` when the payload is empty or malformed.
    """

    if timestamp in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=datetime_timezone.utc)
    except (TypeError, ValueError, OSError):  # pragma: no cover - invalid payload guard
        return None


def to_plain_dict(payload: Any) -> Dict[str, Any]:
    """Convert Stripe objects to dictionaries for easier handling.

    Args:
        payload (Any): Stripe object, dictionary, or plain Python structure.

    Returns:
        Dict[str, Any]: Serializable dictionary representation of ``payload``.
    """

    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    if hasattr(payload, "__dict__"):
        return vars(payload)
    return {}


def resolve_subscription_plan(
    data_object: Dict[str, Any], metadata: Dict[str, Any]
) -> Optional[SubscriptionPlan]:
    """Resolve the subscription plan matching the Stripe payload.

    Args:
        data_object (dict): Stripe subscription or checkout object payload.
        metadata (dict): Metadata accompanying the payload that may reference
            the plan or scope identifiers.

    Returns:
        Optional[SubscriptionPlan]: Plan matched from identifiers, or ``None``
            when the payload cannot be mapped to a configured plan.
    """

    plan_id = metadata.get("plan_id")
    if plan_id:
        plan = SubscriptionPlan.objects.filter(id=plan_id).first()
        if plan:
            return plan

    price_id = None
    items = data_object.get("items") or {}
    items_data = (
        items.get("data") if isinstance(items, dict) else getattr(items, "data", [])
    )
    if items_data:
        first_item = items_data[0]
        price = (
            first_item.get("price")
            if isinstance(first_item, dict)
            else getattr(first_item, "price", None)
        )
        price_id = (
            price.get("id") if isinstance(price, dict) else getattr(price, "id", None)
        )

    if price_id:
        return SubscriptionPlan.objects.filter(stripe_price_id=price_id).first()
    return None


def sync_subscription_from_payload(
    data_object: Dict[str, Any],
    fallback_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Subscription]:
    """Create or update a subscription from Stripe webhook data.

    Args:
        data_object (dict): Stripe subscription payload taken from an event.
        fallback_metadata (Optional[dict]): Metadata to use when the payload does
            not include metadata directly.

    Returns:
        Optional[Subscription]: Subscription instance after synchronisation, or
            ``None`` when required context is missing.
    """

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

    if organisation and subscription.organisation_id != getattr(
        organisation, "id", None
    ):
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
        subscription.save(
            update_fields=list(dict.fromkeys(update_fields + ["updated_at"]))
        )
    return subscription


class PlanListView(APIView):
    """List active subscription plans for public browsing."""

    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):
        """Return all active plans ordered by price.

        Args:
            request (Request): Incoming HTTP request.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Serialized plans sorted from the lowest to highest price.
        """

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price")
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)


class StripeCheckoutSessionView(APIView):
    """Initiate a Stripe Checkout session for a subscription plan."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """Create a Stripe Checkout session tied to the requested plan.

        Args:
            request (Request): Incoming HTTP request containing payload data.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Stripe session payload or error details when configuration
                problems are detected.
        """

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
        except StripeConfigurationError as exc:
            logger.warning("Stripe configuration error when creating checkout: %s", exc)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePlanConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Metadata helps reconcile Stripe events with the correct plan and user
        # scope once the webhook fires.
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

        # The checkout session is configured in subscription mode so Stripe
        # manages the billing cycle and sends subsequent webhook updates.
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
            _require_stripe_secret_key()
            session = stripe.checkout.Session.create(**session_payload)
        except StripeError:  # pragma: no cover - network failures
            logger.exception(
                "Failed to create Stripe checkout session for plan %s", plan.code
            )
            return Response(
                {"detail": "Unable to create Stripe Checkout session."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_payload = {
            "id": session.get("id")
            if isinstance(session, dict)
            else getattr(session, "id", None),
            "url": session.get("url")
            if isinstance(session, dict)
            else getattr(session, "url", None),
            "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
            "plan": SubscriptionPlanSerializer(plan).data,
        }
        return Response(response_payload, status=status.HTTP_200_OK)


class SubscriptionCreateView(APIView):
    """Create a subscription for the requesting user."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """Validate payload and create a subscription.

        Args:
            request (Request): Incoming HTTP request from the client.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Representation of the created subscription.
        """

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
        """Fetch the most relevant active subscription for the user.

        Args:
            request (Request): Request used to identify the authenticated user.

        Returns:
            Optional[Subscription]: Matching subscription prioritising agent
                scope before organisation scope.
        """

        user = request.user
        active_statuses = (
            Subscription.Status.ACTIVE,
            Subscription.Status.PAST_DUE,
            Subscription.Status.INCOMPLETE,
        )

        # Limit to active-like statuses; cancelled subscriptions should not be
        # exposed when retrieving the current subscription.
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
        """Return the user's subscription details.

        Args:
            request (Request): Incoming HTTP request.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Subscription data when found, otherwise a 404 payload.
        """

        del args, kwargs

        subscription = self.get_subscription(request)
        if subscription is None:
            return Response(
                {"detail": "No active subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SubscriptionSerializer(subscription).data)

    def delete(self, request, *args, **kwargs):
        """Cancel the user's subscription when permitted.

        Args:
            request (Request): Incoming HTTP request.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Empty body on success or details describing why the
                subscription could not be cancelled.
        """

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
        """Process the Stripe webhook payload.

        Args:
            request (Request): Incoming webhook request from Stripe.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Response: Empty success response or error payload when the webhook
                cannot be processed.
        """

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
                    _require_stripe_secret_key()
                    subscription_object = stripe.Subscription.retrieve(subscription_id)
                except StripeError:  # pragma: no cover - network failures
                    logger.exception(
                        "Failed to retrieve Stripe subscription %s", subscription_id
                    )
                    return Response(
                        {"detail": "Unable to retrieve subscription."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except StripeConfigurationError as exc:
                    logger.warning(
                        "Stripe configuration error when handling webhook: %s", exc
                    )
                    return Response(
                        {"detail": str(exc)},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                subscription_payload = to_plain_dict(subscription_object)
                sync_subscription_from_payload(subscription_payload, metadata)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            if not data_object:
                logger.warning(
                    "Subscription event received without data: %s", event_dict
                )
                return Response(
                    {"detail": "Subscription data missing."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sync_subscription_from_payload(data_object)
        else:
            logger.info("Received unhandled Stripe event %s", event_type)

        return Response({"detail": "Processed."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Marketplace / PlatformFee views
# ---------------------------------------------------------------------------


class PlatformFeeDetailView(APIView):
    """Retrieve the marketplace invoice attached to a contract.

    This endpoint is used by the front-end to poll fee status and display the
    payment CTA.  Only the parties involved in the contract (agent or
    organisation collaborator) can access this resource.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, contract_id: str):
        """Return the PlatformFee linked to the given contract.

        Args:
            request: Authenticated HTTP request.
            contract_id: UUID of the contract whose fee should be returned.

        Returns:
            Response: Serialized PlatformFee with HTTP 200, or 404 when absent.
        """
        from contracts.models import Contract
        from contracts.serializers import PlatformFeeSerializer

        try:
            contract = Contract.objects.select_related("platform_fee").get(
                id=contract_id
            )
        except Contract.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Restrict to parties in the contract
        user = request.user
        is_collaborator = Collaborator.objects.filter(
            user=user, organisation=contract.organisation
        ).exists()
        agent_profile = getattr(user, "agent_profile", None)
        is_agent = bool(agent_profile and agent_profile == contract.agent)

        if not (user.is_staff or is_collaborator or is_agent):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            fee = contract.platform_fee
        except PlatformFee.DoesNotExist:
            return Response(
                {"detail": "No platform fee generated yet for this contract."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from contracts.serializers import PlatformFeeSerializer  # noqa: F811

        return Response(PlatformFeeSerializer(fee).data)


class MarketplaceStripeWebhookView(APIView):
    """Handle Stripe webhook events specific to the marketplace payment flow.

    Listens for ``payment_intent.succeeded`` events and marks the associated
    :class:`PlatformFee` as PAID, unlocking the DocuSign signing flow.
    """

    permission_classes = (permissions.AllowAny,)
    _WEBHOOK_SETTING = "STRIPE_MARKETPLACE_WEBHOOK_SECRET"

    def post(self, request):
        """Process an incoming Stripe marketplace webhook.

        Args:
            request: Raw HTTP request containing the Stripe event payload.

        Returns:
            Response: 200 on success, 400 on signature failure, 200 for
            unhandled events (so Stripe does not retry them).
        """
        webhook_secret: Optional[str] = getattr(settings, self._WEBHOOK_SETTING, None)
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        try:
            if webhook_secret:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            else:
                event = stripe.Event.construct_from(request.data, stripe.api_key)
        except (ValueError, SignatureVerificationError) as exc:
            logger.warning("Marketplace webhook signature check failed: %s", exc)
            return Response(
                {"detail": "Invalid Stripe signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type: str = event["type"]
        data_object: Dict[str, Any] = event["data"]["object"]

        if event_type == "payment_intent.succeeded":
            payment_intent_id: str = data_object.get("id", "")
            metadata: Dict[str, str] = data_object.get("metadata", {})
            contract_id: str = metadata.get("contract_id", "")

            if not contract_id:
                logger.warning(
                    "payment_intent.succeeded received without contract_id metadata: %s",
                    payment_intent_id,
                )
                return Response({"detail": "Processed."}, status=status.HTTP_200_OK)

            try:
                fee = PlatformFee.objects.select_related("contract").get(
                    contract_id=contract_id
                )
            except PlatformFee.DoesNotExist:
                logger.warning(
                    "No PlatformFee found for contract_id=%s from Stripe event %s",
                    contract_id,
                    payment_intent_id,
                )
                return Response({"detail": "Processed."}, status=status.HTTP_200_OK)

            if fee.status != PlatformFee.Status.PAID:
                fee.mark_paid(stripe_payment_intent_id=payment_intent_id)
                logger.info(
                    "PlatformFee %s marked PAID via Stripe PaymentIntent %s",
                    fee.id,
                    payment_intent_id,
                )

        else:
            logger.debug("Marketplace webhook: unhandled event %s", event_type)

        return Response({"detail": "Processed."}, status=status.HTTP_200_OK)
