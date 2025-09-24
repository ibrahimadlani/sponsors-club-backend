"""Shared permission helpers for account-type specific checks.

The helpers centralise plan-aware gating across the project so views can check
entitlements without duplicating subscription lookups. Each function now
documents the parameters it expects, the values it returns, and the rationale
behind intermediate computations using Google-style docstrings and inline
comments.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from django.apps import apps
from django.db.models import Q

from organisations.models import Collaborator, Organisation
from payments.models import Subscription
from users.models import AgentProfile, User

from .feature_matrix import FEATURE_MATRIX, FeatureRequirement
from .responses import build_error_payload


def get_agent_profile(user: User) -> Optional[AgentProfile]:
    """Fetch the agent profile associated with the user.

    Args:
        user: The authenticated user requesting access.

    Returns:
        Optional[AgentProfile]: The related agent profile if one exists for the
        user, otherwise ``None`` when the account has not been upgraded.
    """
    # Accessing the ``agent_profile`` attribute leverages Django's related
    # object caching. When the relation is missing Django raises a dedicated
    # ``DoesNotExist`` exception rather than returning ``None``.
    try:
        return user.agent_profile  # type: ignore[attr-defined]
    except AgentProfile.DoesNotExist:
        return None


def user_is_agent(user: User) -> bool:
    """Check whether the user account is configured as an agent.

    Args:
        user: The user to inspect.

    Returns:
        bool: ``True`` when the account is marked as an agent profile.
    """
    return getattr(user, "account_type", None) == User.AccountType.AGENT


def user_is_collaborator(user: User) -> bool:
    """Report whether the user collaborates with any organisation.

    Args:
        user: The user whose organisation memberships should be checked.

    Returns:
        bool: ``True`` when the user has at least one collaborator record.
    """
    if not user or not user.is_authenticated:
        return False
    return Collaborator.objects.filter(user=user).exists()


def user_is_collaborator_owner(
    user: User, organisation: Optional[Organisation] = None
) -> bool:
    """Evaluate whether the user owns a collaboration workspace.

    Args:
        user: The user claiming ownership.
        organisation: Optionally limit the check to a single organisation.

    Returns:
        bool: ``True`` when the user is registered as an owner for the
        provided organisation or for any organisation when ``organisation``
        is ``None``.
    """
    # The collaborator relation stores ownership as an enum value on the join
    # table, so the check simply filters the mapping for the OWNER role.
    filters = Q(user=user, role=Collaborator.Role.OWNER)
    if organisation is not None:
        filters &= Q(organisation=organisation)
    return Collaborator.objects.filter(filters).exists()


def get_active_agent_subscription(user: User) -> Optional[Subscription]:
    """Retrieve the most recent active subscription for an agent.

    Args:
        user: The agent user requesting an entitlement check.

    Returns:
        Optional[Subscription]: The newest active subscription if the user has
        one, otherwise ``None`` when the agent is on the free tier.
    """
    agent_profile = get_agent_profile(user)
    if not agent_profile:
        return None
    # Subscriptions are ordered by their period end so the first record reflects
    # the current plan when multiple entries exist.
    return (
        Subscription.objects.filter(
            agent=agent_profile,
            status=Subscription.Status.ACTIVE,
        )
        .select_related("plan")
        .order_by("-current_period_end")
        .first()
    )


def get_active_organisation_subscriptions(user: User) -> list[Subscription]:
    """List active organisation subscriptions associated with the user.

    Args:
        user: The collaborator whose organisations should be inspected.

    Returns:
        list[Subscription]: Active subscriptions sorted by most recent expiry
        date. An empty list is returned when the user has no collaborations or
        none of the organisations are subscribed.
    """
    organisation_ids = list(
        Collaborator.objects.filter(user=user).values_list("organisation_id", flat=True)
    )
    if not organisation_ids:
        return []
    return list(
        Subscription.objects.filter(
            organisation_id__in=organisation_ids,
            status=Subscription.Status.ACTIVE,
        )
        .select_related("plan")
        .order_by("-current_period_end")
    )


def _mapping_has_feature(
    features: Mapping[str, object],
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Check whether a mapping contains a feature with acceptable values.

    Args:
        features: The mapping of feature codes to configured values.
        feature_key: The feature to look up.
        allowed_values: Optional constraint restricting which values count as a
            match.

    Returns:
        bool: ``True`` when the feature exists and passes the value filter.
    """
    if feature_key not in features:
        return False
    value = features[feature_key]
    if allowed_values is None:
        return bool(value)
    return value in allowed_values


def _subscription_has_feature(
    subscription: Subscription,
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Check whether the plan tied to a subscription exposes a feature.

    Args:
        subscription: The subscription whose plan should be evaluated.
        feature_key: The feature flag to validate.
        allowed_values: Optional collection limiting accepted values.

    Returns:
        bool: ``True`` when the plan defines the feature and its value matches
        any provided constraints.
    """
    if subscription.plan and isinstance(subscription.plan.features, dict):
        features = dict(subscription.plan.features)
    else:
        features = {}

    plan = subscription.plan
    if plan is not None:
        if getattr(plan, "max_athletes", None) is not None:
            features.setdefault("max_athletes", plan.max_athletes)
        if getattr(plan, "max_collaborators", None) is not None:
            features.setdefault("max_collaborators", plan.max_collaborators)

    return _mapping_has_feature(features, feature_key, allowed_values)


def agent_has_feature(
    user: User,
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Confirm that the agent user has a plan providing the feature.

    Args:
        user: The agent subject to the entitlement check.
        feature_key: The feature flag to test.
        allowed_values: Optional constraint restricting acceptable values.

    Returns:
        bool: ``True`` when the feature is available either through a paid plan
        or the default free tier fallback.
    """
    subscription = get_active_agent_subscription(user)
    if subscription:
        return _subscription_has_feature(subscription, feature_key, allowed_values)

    fallback_features = _load_plan_features("agent-free", DEFAULT_AGENT_FEATURES)
    return _mapping_has_feature(fallback_features, feature_key, allowed_values)


def collaborator_has_feature(
    user: User,
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Confirm that a collaborator has access to a feature.

    Args:
        user: The collaborator whose organisations should be inspected.
        feature_key: The feature flag being requested.
        allowed_values: Optional constraint restricting acceptable values.

    Returns:
        bool: ``True`` when a subscribed organisation grants the feature or the
        default starter plan covers it when no subscriptions are active.
    """
    if not user_is_collaborator(user):
        return False
    subscriptions = get_active_organisation_subscriptions(user)
    for subscription in subscriptions:
        # Iterate over the organisations in priority order, returning early as
        # soon as a matching feature is located to avoid redundant queries.
        if _subscription_has_feature(subscription, feature_key, allowed_values):
            return True
    if subscriptions:
        return False

    fallback_features = _load_plan_features("org-starter", DEFAULT_ORG_FEATURES)
    return _mapping_has_feature(fallback_features, feature_key, allowed_values)


def agent_meets_requirement(user: User, requirement: FeatureRequirement) -> bool:
    """Evaluate whether an agent satisfies a feature requirement.

    Args:
        user: The agent being evaluated.
        requirement: The entitlement definition outlining the required feature.

    Returns:
        bool: ``True`` when the agent has the feature specified by the
        requirement.
    """
    return agent_has_feature(user, requirement.key, requirement.allowed_values)


def collaborator_meets_requirement(user: User, requirement: FeatureRequirement) -> bool:
    """Evaluate whether a collaborator satisfies a feature requirement.

    Args:
        user: The collaborator being evaluated.
        requirement: The entitlement definition outlining the required feature.

    Returns:
        bool: ``True`` when the collaborator's organisations expose the feature
        defined in the requirement.
    """
    return collaborator_has_feature(user, requirement.key, requirement.allowed_values)


DEFAULT_AGENT_FEATURES = {
    "max_athletes": 1,
    "messaging_tier": "none",
    "max_messages_per_month": 0,
    "search_visibility_pct": 50,
    "stats_tier": "basic",
    "comparative_stats": False,
    "agent_subscription_management": True,
    "contract_tools": "disabled",
    "notification_center": False,
}

DEFAULT_ORG_FEATURES = {
    "max_follows": 10,
    "max_collaborators": 3,
    "collaborator_invites": True,
    "organisation_subscription_management": True,
    "athlete_stats_scope": "engagement",
    "data_access": ["follows", "engagement"],
    "contract_tools": "disabled",
    "notification_center": True,
}


def _load_plan_features(plan_code: str, fallback: dict) -> dict:
    """Load features for a predefined plan code.

    Args:
        plan_code: The canonical plan identifier stored in the payments app.
        fallback: The default features to merge in when the database entry is
            missing or incomplete.

    Returns:
        dict: Combined feature configuration with sensible defaults applied.
    """
    subscription_plan_model = apps.get_model("payments", "SubscriptionPlan")
    plan = subscription_plan_model.objects.filter(code=plan_code).first()

    features: dict = {}
    if plan and isinstance(plan.features, dict):
        features.update(plan.features)

    if plan is not None:
        # Some features are stored as dedicated columns rather than inside the
        # JSON ``features`` payload. ``setdefault`` preserves explicitly defined
        # JSON values while still exposing the column-based fields.
        if getattr(plan, "max_athletes", None) is not None:
            features.setdefault("max_athletes", plan.max_athletes)
        if getattr(plan, "max_collaborators", None) is not None:
            features.setdefault("max_collaborators", plan.max_collaborators)

    if features:
        # When the plan overrides only a subset of defaults, merge the fallback
        # to ensure callers always receive a complete mapping for UI rendering.
        for key, value in fallback.items():
            features.setdefault(key, value)
        return features

    return fallback.copy()


def get_agent_plan_features(user: User) -> dict:
    """Return the feature configuration derived from the agent's plan.

    Args:
        user: The agent whose subscription features should be returned.

    Returns:
        dict: The features exposed by the current plan, defaulting to the free
        tier when no subscription is active.
    """
    subscription = get_active_agent_subscription(user)
    if subscription and isinstance(subscription.plan.features, dict):
        return subscription.plan.features
    return _load_plan_features("agent-free", DEFAULT_AGENT_FEATURES)


def get_collaborator_plan_features(
    user: User,
    organisation: Optional[Organisation] = None,
) -> dict:
    """Retrieve plan features for a collaborator.

    Args:
        user: The collaborator whose subscriptions should be considered.
        organisation: Optionally limit the features to a specific organisation.

    Returns:
        dict: The derived feature mapping either from a live subscription or the
        default organisation starter plan when no subscription is active.
    """
    subscriptions = get_active_organisation_subscriptions(user)
    selected = None
    if organisation is not None:
        for sub in subscriptions:
            if sub.organisation_id == organisation.id:
                selected = sub
                break
    if selected is None:
        selected = subscriptions[0] if subscriptions else None
    if selected and isinstance(selected.plan.features, dict):
        return selected.plan.features
    return _load_plan_features("org-starter", DEFAULT_ORG_FEATURES)


def user_feature_requirement(
    user: User,
    feature_code: str,
) -> tuple[Optional[FeatureRequirement], bool]:
    """Resolve a feature requirement and whether the user passes it.

    Args:
        user: The authenticated user requesting the capability.
        feature_code: The matrix entry describing the feature requirement.

    Returns:
        tuple[Optional[FeatureRequirement], bool]: The resolved requirement and
        a boolean describing whether the user satisfies it. ``(None, False)``
        is returned for unauthenticated users or unsupported account types.
    """
    if not user or not user.is_authenticated:
        return None, False

    account_type = getattr(user, "account_type", None)
    requirement: Optional[FeatureRequirement] = None
    granted = False

    if account_type == User.AccountType.AGENT:
        requirement = FEATURE_MATRIX["agent"].get(feature_code)
        if requirement is None:
            return None, True
        granted = agent_meets_requirement(user, requirement)
    elif account_type == User.AccountType.COLLABORATOR:
        requirement = FEATURE_MATRIX["collaborator"].get(feature_code)
        if requirement is None:
            return None, True
        granted = collaborator_meets_requirement(user, requirement)
    else:
        requirement = None
        granted = False

    return requirement, granted


def feature_status_for_user(user: User) -> list[dict]:
    """Describe the feature entitlements available to the user.

    Args:
        user: The authenticated user requesting a summary view.

    Returns:
        list[dict]: A collection of dictionaries describing whether each
        entitlement is granted, including messaging for UI rendering.
    """
    if not user or not user.is_authenticated:
        return []

    account_type = getattr(user, "account_type", None)
    matrix_key = None
    if account_type == User.AccountType.AGENT:
        matrix_key = "agent"
    elif account_type == User.AccountType.COLLABORATOR:
        matrix_key = "collaborator"

    if matrix_key is None or matrix_key not in FEATURE_MATRIX:
        return []

    statuses: list[dict] = []
    for code, requirement in FEATURE_MATRIX[matrix_key].items():
        if matrix_key == "agent":
            granted = agent_meets_requirement(user, requirement)
        else:
            granted = collaborator_meets_requirement(user, requirement)

        statuses.append(
            {
                "code": code,
                "label": requirement.label or code.replace("_", " ").title(),
                "description": requirement.description,
                "granted": granted,
                "required_feature": requirement.key,
                "allowed_values": requirement.allowed_values,
                "upgrade_url": requirement.upgrade_url,
                "recommended_plans": list(requirement.recommended_plans),
            }
        )

    return statuses


def requirement_denied_payload(
    requirement: FeatureRequirement, default_detail: str
) -> dict:
    """Build a standardised denial payload for unmet feature requirements.

    Args:
        requirement: The entitlement configuration that blocked the request.
        default_detail: Fallback human-readable message for the denial.
        
    Returns:
        dict: Serialisable payload describing the requirement to clients.
    """

    message = requirement.denied_message or default_detail
    return build_error_payload(
        message,
        code="feature_requirement_denied",
        required_feature=requirement.key,
        allowed_values=requirement.allowed_values,
        upgrade_url=requirement.upgrade_url,
        recommended_plans=list(requirement.recommended_plans),
    )



