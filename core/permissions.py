"""Shared permission helpers for account-type specific checks."""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from django.apps import apps
from django.db.models import Q

from organisations.models import Collaborator, Organisation
from payments.models import Subscription
from users.models import AgentProfile, User

from .feature_matrix import FEATURE_MATRIX, FeatureRequirement


def get_agent_profile(user: User) -> Optional[AgentProfile]:
    """Return the agent profile for the given user if it exists."""
    try:
        return user.agent_profile  # type: ignore[attr-defined]
    except AgentProfile.DoesNotExist:  # pylint: disable=no-member
        return None


def user_is_agent(user: User) -> bool:
    """Check whether the user account is configured as an agent."""
    return getattr(user, 'account_type', None) == User.AccountType.AGENT


def user_is_collaborator(user: User) -> bool:
    """Return True when the user belongs to at least one organisation."""
    if not user or not user.is_authenticated:
        return False
    return Collaborator.objects.filter(user=user).exists()  # pylint: disable=no-member


def user_is_collaborator_owner(user: User, organisation: Optional[Organisation] = None) -> bool:
    """Return True when the user owns the provided organisation (or any organisation)."""
    filters = Q(user=user, role=Collaborator.Role.OWNER)
    if organisation is not None:
        filters &= Q(organisation=organisation)
    return Collaborator.objects.filter(filters).exists()  # pylint: disable=no-member


def get_active_agent_subscription(user: User) -> Optional[Subscription]:
    """Return the most recent active subscription for the agent user."""
    agent_profile = get_agent_profile(user)
    if not agent_profile:
        return None
    return (
        Subscription.objects.filter(  # pylint: disable=no-member
            agent=agent_profile,
            status=Subscription.Status.ACTIVE,
        )
        .select_related('plan')
        .order_by('-current_period_end')
        .first()
    )


def get_active_organisation_subscriptions(user: User) -> list[Subscription]:
    """Return active organisation subscriptions linked to the user via collaborations."""
    organisation_ids = list(
        Collaborator.objects.filter(user=user)  # pylint: disable=no-member
        .values_list('organisation_id', flat=True)
    )
    if not organisation_ids:
        return []
    return list(
        Subscription.objects.filter(  # pylint: disable=no-member
            organisation_id__in=organisation_ids,
            status=Subscription.Status.ACTIVE,
        )
        .select_related('plan')
        .order_by('-current_period_end')
    )


def _mapping_has_feature(
    features: Mapping[str, object],
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
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
    if subscription.plan and isinstance(subscription.plan.features, dict):
        features = dict(subscription.plan.features)
    else:
        features = {}

    plan = subscription.plan
    if plan is not None:
        if getattr(plan, 'max_athletes', None) is not None:
            features.setdefault('max_athletes', plan.max_athletes)
        if getattr(plan, 'max_collaborators', None) is not None:
            features.setdefault('max_collaborators', plan.max_collaborators)

    return _mapping_has_feature(features, feature_key, allowed_values)


def agent_has_feature(
    user: User,
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Check whether the agent user has an active subscription with the specified feature."""
    subscription = get_active_agent_subscription(user)
    if subscription:
        return _subscription_has_feature(subscription, feature_key, allowed_values)

    fallback_features = _load_plan_features('agent-free', DEFAULT_AGENT_FEATURES)
    return _mapping_has_feature(fallback_features, feature_key, allowed_values)


def collaborator_has_feature(
    user: User,
    feature_key: str,
    allowed_values: Optional[Sequence[str]] = None,
) -> bool:
    """Check whether any organisation subscription grants the feature to the collaborator."""
    if not user_is_collaborator(user):
        return False
    subscriptions = get_active_organisation_subscriptions(user)
    for subscription in subscriptions:
        if _subscription_has_feature(subscription, feature_key, allowed_values):
            return True
    if subscriptions:
        return False

    fallback_features = _load_plan_features('org-starter', DEFAULT_ORG_FEATURES)
    return _mapping_has_feature(fallback_features, feature_key, allowed_values)


def agent_meets_requirement(user: User, requirement: FeatureRequirement) -> bool:
    """Evaluate whether an agent satisfies the provided feature requirement."""

    return agent_has_feature(user, requirement.key, requirement.allowed_values)


def collaborator_meets_requirement(user: User, requirement: FeatureRequirement) -> bool:
    """Evaluate whether a collaborator satisfies the provided feature requirement."""

    return collaborator_has_feature(user, requirement.key, requirement.allowed_values)


DEFAULT_AGENT_FEATURES = {
    'max_athletes': 1,
    'messaging_tier': 'none',
    'max_messages_per_month': 0,
    'search_visibility_pct': 50,
    'stats_tier': 'basic',
    'comparative_stats': False,
    'agent_subscription_management': True,
    'contract_tools': 'disabled',
    'notification_center': False,
}

DEFAULT_ORG_FEATURES = {
    'max_follows': 10,
    'max_collaborators': 3,
    'collaborator_invites': True,
    'organisation_subscription_management': True,
    'athlete_stats_scope': 'engagement',
    'data_access': ['follows', 'engagement'],
    'contract_tools': 'disabled',
    'notification_center': True,
}


def _load_plan_features(plan_code: str, fallback: dict) -> dict:
    subscription_plan_model = apps.get_model('payments', 'SubscriptionPlan')
    plan = subscription_plan_model.objects.filter(code=plan_code).first()

    features: dict = {}
    if plan and isinstance(plan.features, dict):
        features.update(plan.features)

    if plan is not None:
        if getattr(plan, 'max_athletes', None) is not None:
            features.setdefault('max_athletes', plan.max_athletes)
        if getattr(plan, 'max_collaborators', None) is not None:
            features.setdefault('max_collaborators', plan.max_collaborators)

    if features:
        for key, value in fallback.items():
            features.setdefault(key, value)
        return features

    return fallback.copy()


def get_agent_plan_features(user: User) -> dict:
    """Return the feature configuration derived from the agent's current plan."""
    subscription = get_active_agent_subscription(user)
    if subscription and isinstance(subscription.plan.features, dict):
        return subscription.plan.features
    return _load_plan_features('agent-free', DEFAULT_AGENT_FEATURES)


def get_collaborator_plan_features(
    user: User,
    organisation: Optional[Organisation] = None,
) -> dict:
    """Return feature configuration for the collaborator, optionally scoped to an organisation."""
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
    return _load_plan_features('org-starter', DEFAULT_ORG_FEATURES)


def user_feature_requirement(
    user: User,
    feature_code: str,
) -> tuple[Optional[FeatureRequirement], bool]:
    """Return the requirement for the given feature code and whether the user satisfies it."""

    if not user or not user.is_authenticated:
        return None, False

    account_type = getattr(user, 'account_type', None)
    requirement: Optional[FeatureRequirement] = None
    granted = False

    if account_type == User.AccountType.AGENT:
        requirement = FEATURE_MATRIX['agent'].get(feature_code)
        if requirement is None:
            return None, True
        granted = agent_meets_requirement(user, requirement)
    elif account_type == User.AccountType.COLLABORATOR:
        requirement = FEATURE_MATRIX['collaborator'].get(feature_code)
        if requirement is None:
            return None, True
        granted = collaborator_meets_requirement(user, requirement)
    else:
        requirement = None
        granted = False

    return requirement, granted


def feature_status_for_user(user: User) -> list[dict]:
    """Return a list describing each feature entitlement for the current user."""

    if not user or not user.is_authenticated:
        return []

    account_type = getattr(user, 'account_type', None)
    matrix_key = None
    if account_type == User.AccountType.AGENT:
        matrix_key = 'agent'
    elif account_type == User.AccountType.COLLABORATOR:
        matrix_key = 'collaborator'

    if matrix_key is None or matrix_key not in FEATURE_MATRIX:
        return []

    statuses: list[dict] = []
    for code, requirement in FEATURE_MATRIX[matrix_key].items():
        if matrix_key == 'agent':
            granted = agent_meets_requirement(user, requirement)
        else:
            granted = collaborator_meets_requirement(user, requirement)

        statuses.append({
            'code': code,
            'label': requirement.label or code.replace('_', ' ').title(),
            'description': requirement.description,
            'granted': granted,
            'required_feature': requirement.key,
            'allowed_values': requirement.allowed_values,
            'upgrade_url': requirement.upgrade_url,
            'recommended_plans': list(requirement.recommended_plans),
        })

    return statuses


def requirement_denied_payload(requirement: FeatureRequirement, default_detail: str) -> dict:
    """Build a standardised denial payload for unmet feature requirements."""

    return {
        'detail': requirement.denied_message or default_detail,
        'required_feature': requirement.key,
        'allowed_values': requirement.allowed_values,
        'upgrade_url': requirement.upgrade_url,
        'recommended_plans': list(requirement.recommended_plans),
    }
