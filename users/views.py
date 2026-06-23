"""API views for user registration and self-service endpoints."""

import statistics
import uuid
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from django.apps import apps
from django.conf import settings as django_settings

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import (
    DEFAULT_AGENT_FEATURES,
    DEFAULT_ORG_FEATURES,
    feature_status_for_user,
    get_active_agent_subscription,
    get_active_organisation_subscriptions,
    get_agent_plan_features,
    get_collaborator_plan_features,
)
from .serializers import (
    EmailVerificationConfirmSerializer,
    MeUpdateSerializer,
    RegisterSerializer,
    RolesDataBuilder,
    RolesSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Public endpoint allowing creation of a new user account."""

    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        """Persist a new user and return the serialized representation."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = UserSerializer(user, context=self.get_serializer_context()).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class MeView(generics.RetrieveUpdateAPIView):
    """Authenticated view for retrieving or updating the current user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        """Return serializer tailored to read or update operations."""
        if self.request.method in ("PUT", "PATCH"):
            return MeUpdateSerializer
        return UserSerializer

    def get_object(self):
        """Return the authenticated user instance."""
        return self.request.user


class MeRolesView(APIView):
    """Provide information about the roles associated with the user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *_args, **_kwargs):
        """Return a structured payload describing the user's roles."""
        payload = RolesDataBuilder(request.user).build()
        serializer = RolesSerializer(payload)
        return Response(serializer.data)


class MeEntitlementsView(APIView):
    """Expose the feature entitlements granted to the authenticated user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *_args, **_kwargs):
        """Return the current user's feature entitlements and upgrade guidance."""
        user = request.user
        features = feature_status_for_user(user)
        return Response(
            {
                "account_type": getattr(user, "account_type", None),
                "features": features,
            }
        )


class VerifyEmailView(APIView):
    """Allow users to confirm their email address via verification token."""

    permission_classes = (permissions.AllowAny,)

    def post(self, request, *_args, **_kwargs):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Email address verified."})


class TokenObtainPairWithProfileSerializer(TokenObtainPairSerializer):
    """Extend JWT payload with user profile claims.

    Adds first/last names, email, account role, and plan when available.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["sub"] = str(getattr(user, "id", uuid.uuid4()))
        token["email"] = getattr(user, "email", None)
        token["first_name"] = getattr(user, "first_name", None)
        token["last_name"] = getattr(user, "last_name", None)
        token["role"] = getattr(user, "account_type", None)
        token["permissions"] = {
            "is_staff": bool(getattr(user, "is_staff", False)),
            "is_superuser": bool(getattr(user, "is_superuser", False)),
        }
        token["meta"] = _build_meta_payload(token)

        role = token.get("role")
        if role == getattr(user.__class__.AccountType, "AGENT", "AGENT"):
            for key, value in _build_agent_claims(user).items():
                token[key] = value
        elif role == getattr(
            user.__class__.AccountType, "COLLABORATOR", "COLLABORATOR"
        ):
            for key, value in _build_collaborator_claims(user).items():
                token[key] = value
        else:
            token["profile"] = {}
            token["plan"] = {}
            token["entitlements"] = {}
            token["onboarding"] = {}
        return token


class TokenObtainPairWithProfileView(TokenObtainPairView):
    serializer_class = TokenObtainPairWithProfileSerializer


def _build_meta_payload(token: dict) -> dict:
    """Return metadata describing issuance details for the JWT."""

    issued_at = token.get("iat")
    expires_at = token.get("exp")
    return {
        "issued_at": _timestamp_to_iso(issued_at),
        "expires_at": _timestamp_to_iso(expires_at),
        "api_version": getattr(django_settings, "API_VERSION", "v1"),
        "app_env": getattr(
            django_settings,
            "APP_ENV",
            "development" if getattr(django_settings, "DEBUG", False) else "production",
        ),
    }


def _build_agent_claims(user) -> dict:
    """Assemble agent-specific JWT payload sections."""

    agent_profile = getattr(user, "agent_profile", None)
    athletes = []
    followers_total = 0
    engagement_values: list[float] = []
    most_followed: Optional[dict[str, str]] = None

    Athlete = _get_model("athletes", "Athlete")
    if agent_profile and Athlete is not None:
        athlete_qs = (
            Athlete.objects.filter(agent=agent_profile)
            .select_related("sport")
            .order_by("full_name")
        )
        for athlete in athlete_qs:
            sport_name = getattr(getattr(athlete, "sport", None), "name", None)
            followers = int(getattr(athlete, "followers_count_cached", 0) or 0)
            engagement = getattr(athlete, "engagement_rate_cached", None)
            engagement_value = _coerce_float(engagement)
            if engagement_value is not None:
                engagement_values.append(engagement_value)
            athlete_payload = {
                "id": str(getattr(athlete, "id", uuid.uuid4())),
                "full_name": getattr(athlete, "full_name", None),
                "slug": getattr(athlete, "slug", None),
                "sport": sport_name,
                "followers_count_cached": followers,
                "engagement_rate_cached": engagement_value,
            }
            athletes.append(athlete_payload)
            followers_total += followers
            if not most_followed or followers > most_followed.get("followers", -1):
                most_followed = {
                    "id": athlete_payload["id"],
                    "name": athlete_payload["full_name"],
                    "followers": followers,
                }

    avg_engagement = (
        round(statistics.fmean(engagement_values), 2) if engagement_values else None
    )
    most_followed_payload = None
    if most_followed:
        most_followed_payload = {
            "id": most_followed["id"],
            "name": most_followed.get("name"),
        }

    subscription = get_active_agent_subscription(user)
    plan_obj = (
        subscription.plan if subscription else _get_subscription_plan("agent-free")
    )
    plan_features = _merge_feature_defaults(
        get_agent_plan_features(user),
        DEFAULT_AGENT_FEATURES,
    )
    max_athletes_value = _coerce_numeric(getattr(plan_obj, "max_athletes", None))
    if max_athletes_value is None:
        max_athletes_value = _coerce_numeric(plan_features.get("max_athletes"))
    max_collaborators_value = _coerce_numeric(
        getattr(plan_obj, "max_collaborators", None)
    )
    if max_collaborators_value is None:
        max_collaborators_value = _coerce_numeric(
            plan_features.get("max_collaborators", 0)
        )

    plan_payload = _build_plan_payload(
        plan_obj=plan_obj,
        plan_features=plan_features,
        is_active=bool(subscription) if subscription is not None else True,
        current_period_end=getattr(subscription, "current_period_end", None),
        fallback_code="agent-free",
        fallback_name="Agent Free",
        extra_fields={
            "max_athletes": max_athletes_value,
            "max_collaborators": max_collaborators_value,
        },
    )

    entitlements = _build_entitlements_map(user, plan_features)

    Collaborator = _get_model("organisations", "Collaborator")
    has_collaboration = False
    if Collaborator is not None:
        has_collaboration = Collaborator.objects.filter(user=user).exists()

    profile_payload = {
        "agent_profile_id": str(getattr(agent_profile, "id", ""))
        if agent_profile
        else None,
        "display_name": str(user),
        "is_self_represented": bool(
            getattr(agent_profile, "is_self_represented", False)
        ),
        "bio": getattr(agent_profile, "bio", "") if agent_profile else "",
        "athletes_count": len(athletes),
        "athletes": athletes,
    }

    stats_payload = {
        "followers_total": followers_total,
        "avg_engagement_rate": avg_engagement,
        "most_followed_athlete": most_followed_payload,
    }

    onboarding_payload = {
        "needs_athlete": len(athletes) == 0,
        "has_active_subscription": bool(subscription),
        "has_collaboration": has_collaboration,
    }

    return {
        "profile": profile_payload,
        "plan": plan_payload,
        "entitlements": entitlements,
        "onboarding": onboarding_payload,
        "stats": stats_payload,
    }


def _build_collaborator_claims(user) -> dict:
    """Assemble collaborator-specific JWT payload sections."""

    Collaborator = _get_model("organisations", "Collaborator")
    collaborations: list[Any] = []
    if Collaborator is not None:
        collaborations = list(
            Collaborator.objects.filter(user=user).select_related("organisation")
        )

    collaborator_ids = [str(collab.id) for collab in collaborations]
    primary = collaborations[0] if collaborations else None
    organisations = [
        collab.organisation for collab in collaborations if collab.organisation
    ]

    profile_payload: Dict[str, Any] = {
        "collaborator_ids": collaborator_ids,
        "primary_collaboration": None,
        "organisations_count": len({getattr(org, "id", None) for org in organisations}),
        "is_owner": any(
            getattr(collab, "role", None) == Collaborator.Role.OWNER
            for collab in collaborations
        )
        if Collaborator is not None
        else False,
        "is_member": any(
            getattr(collab, "role", None) == Collaborator.Role.MEMBER
            for collab in collaborations
        )
        if Collaborator is not None
        else False,
    }

    if primary and getattr(primary, "organisation", None):
        organisation = primary.organisation
        profile_payload["primary_collaboration"] = {
            "collaborator_id": str(getattr(primary, "id", "")),
            "organisation_id": str(getattr(organisation, "id", "")),
            "organisation_name": getattr(organisation, "name", None),
            "organisation_slug": getattr(organisation, "slug", None),
            "role": getattr(primary, "role", None),
            "job_title": getattr(primary, "job_title", None),
            "industry": getattr(organisation, "industry", None),
            "country": getattr(organisation, "address_country", None),
        }

    subscriptions = get_active_organisation_subscriptions(user)
    subscription_lookup = {
        getattr(sub, "organisation_id", None): sub for sub in subscriptions
    }
    selected_subscription = None
    if primary is not None:
        selected_subscription = subscription_lookup.get(
            getattr(primary, "organisation_id", None)
        )
    if selected_subscription is None and subscriptions:
        selected_subscription = subscriptions[0]

    plan_obj = (
        selected_subscription.plan
        if selected_subscription
        else _get_subscription_plan("org-starter")
    )
    target_org = getattr(primary, "organisation", None)
    plan_features = _merge_feature_defaults(
        get_collaborator_plan_features(user, organisation=target_org),
        DEFAULT_ORG_FEATURES,
    )
    max_collaborators_value = _coerce_numeric(
        getattr(plan_obj, "max_collaborators", None)
    )
    if max_collaborators_value is None:
        max_collaborators_value = _coerce_numeric(
            plan_features.get("max_collaborators")
        )

    plan_payload = _build_plan_payload(
        plan_obj=plan_obj,
        plan_features=plan_features,
        is_active=(selected_subscription is not None)
        if selected_subscription is not None
        else True,
        current_period_end=getattr(selected_subscription, "current_period_end", None),
        fallback_code="org-starter",
        fallback_name="Organisation Starter",
        extra_fields={
            "max_collaborators": max_collaborators_value,
            "max_follows": _coerce_numeric(plan_features.get("max_follows")),
        },
    )

    entitlements = _build_entitlements_map(user, plan_features)

    onboarding_payload = {
        "needs_organisation": not collaborations,
        "is_owner": profile_payload.get("is_owner", False),
        "has_active_subscription": selected_subscription is not None,
    }

    activity_payload = _build_collaborator_activity(collaborations, organisations, user)

    return {
        "profile": profile_payload,
        "plan": plan_payload,
        "entitlements": entitlements,
        "onboarding": onboarding_payload,
        "activity": activity_payload,
    }


def _build_plan_payload(
    *,
    plan_obj: Optional[Any],
    plan_features: Dict[str, Any],
    is_active: bool,
    current_period_end: Optional[Any],
    fallback_code: str,
    fallback_name: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> dict:
    """Serialize plan metadata shared by agent and collaborator payloads."""

    features = _sanitize_mapping(plan_features)
    if extra_fields:
        for key, value in extra_fields.items():
            if value is not None:
                features[key] = value

    price = getattr(plan_obj, "price", None)
    currency = getattr(plan_obj, "currency", None)
    price_value = _coerce_float(price)
    if price_value is None:
        price_value = 0.0

    plan_payload = {
        "code": getattr(plan_obj, "code", fallback_code),
        "name": getattr(plan_obj, "name", fallback_name),
        "price": price_value,
        "currency": currency or "EUR",
        "is_active": bool(getattr(plan_obj, "is_active", is_active)),
        "current_period_end": _datetime_to_iso(current_period_end),
        "features": features,
    }

    if "max_athletes" in features:
        plan_payload["max_athletes"] = features["max_athletes"]
    if "max_collaborators" in features:
        plan_payload["max_collaborators"] = features["max_collaborators"]
    if "max_follows" in features:
        plan_payload["max_follows"] = features["max_follows"]

    return plan_payload


def _build_entitlements_map(user, plan_features: Dict[str, Any]) -> dict:
    """Transform entitlement status list into a mapping keyed by feature code."""

    entitlements: Dict[str, Dict[str, Any]] = {}
    statuses = feature_status_for_user(user)
    for feature_status in statuses:
        suggestion = None
        if not feature_status.get("granted") and feature_status.get(
            "recommended_plans"
        ):
            suggestion = feature_status["recommended_plans"][0]
        entry: Dict[str, Any] = {
            "granted": bool(feature_status.get("granted")),
            "upgrade_suggestion": suggestion,
        }
        if suggestion:
            entry["suggested_plan"] = suggestion
        plan_value = plan_features.get(feature_status.get("required_feature"))
        numeric_value = _coerce_numeric(plan_value)
        if numeric_value is not None:
            entry["limit"] = numeric_value
        upgrade_url = feature_status.get("upgrade_url")
        if not feature_status.get("granted") and upgrade_url:
            entry["upgrade_url"] = upgrade_url
        entitlements[feature_status.get("code")] = entry
    return entitlements


def _build_collaborator_activity(
    collaborations: Iterable[Any], organisations: Iterable[Any], user
) -> dict:
    """Calculate collaborator activity metrics exposed in the JWT."""

    Follow = _get_model("follows", "Follow")
    Contract = _get_model("contracts", "Contract")

    collaborator_ids = [getattr(collab, "id", None) for collab in collaborations]
    organisation_ids = [getattr(org, "id", None) for org in organisations]

    follows_count = 0
    if Follow is not None and collaborator_ids:
        follows_count = Follow.objects.filter(
            collaborator_id__in=collaborator_ids
        ).count()

    active_contracts_count = 0
    pending_contracts_count = 0
    if Contract is not None and organisation_ids:
        active_contracts_count = Contract.objects.filter(
            organisation_id__in=organisation_ids,
            status=Contract.Status.ACTIVE,
        ).count()
        pending_contracts_count = Contract.objects.filter(
            organisation_id__in=organisation_ids,
            status__in=[
                Contract.Status.DRAFT,
                Contract.Status.NEGOTIATION,
                Contract.Status.AGREEMENT,
                Contract.Status.LEGAL_REVIEW,
                Contract.Status.SIGNING,
            ],
        ).count()

    unread_notifications = getattr(user, "notifications", None)
    if unread_notifications is not None:
        unread_notifications = user.notifications.filter(is_read=False).count()
    else:
        unread_notifications = 0

    return {
        "follows_count": follows_count,
        "active_contracts_count": active_contracts_count,
        "pending_contracts_count": pending_contracts_count,
        "unread_notifications": unread_notifications,
    }


def _merge_feature_defaults(features: Optional[dict], defaults: dict) -> Dict[str, Any]:
    """Merge plan feature values with domain defaults without mutating inputs."""

    merged: Dict[str, Any] = {}
    if isinstance(features, dict):
        merged.update(features)
    for key, value in defaults.items():
        merged.setdefault(key, value)
    return merged


def _sanitize_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """Convert mapping values to JSON friendly primitives."""

    sanitized: Dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            sanitized[key] = _sanitize_mapping(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_mapping(item)
                if isinstance(item, dict)
                else _sanitize_value(item)
                for item in value
            ]
        else:
            sanitized[key] = _sanitize_value(value)
    return sanitized


def _sanitize_value(value: Any) -> Any:
    """Coerce non-serialisable values into JSON friendly representations."""

    if isinstance(value, Decimal):
        return _coerce_float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _coerce_float(value: Any) -> Optional[float]:
    """Convert decimal or numeric values to float when possible."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return None


def _coerce_numeric(value: Any) -> Optional[float]:
    """Return numeric representation or ``None`` when conversion is unsafe."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return None


def _timestamp_to_iso(timestamp: Any) -> Optional[str]:
    """Convert a JWT timestamp (seconds) to ISO 8601 format."""

    if timestamp is None:
        return None
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
    except (ValueError, OSError, TypeError):  # pragma: no cover - defensive guard
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _datetime_to_iso(value: Any) -> Optional[str]:
    """Convert a datetime instance to ISO 8601 with UTC normalisation."""

    if value is None:
        return None
    if not hasattr(value, "astimezone"):
        return None
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _get_model(app_label: str, model_name: str):
    """Safely retrieve a Django model class."""

    try:
        return apps.get_model(app_label, model_name)
    except LookupError:  # pragma: no cover - guard for optional apps
        return None


def _get_subscription_plan(code: str):
    """Return the subscription plan for a fallback code when available."""

    SubscriptionPlan = _get_model("payments", "SubscriptionPlan")
    if SubscriptionPlan is None:
        return None
    return SubscriptionPlan.objects.filter(code=code).first()
