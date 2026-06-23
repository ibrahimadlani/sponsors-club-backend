from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from core import permissions
from core.feature_matrix import FEATURE_MATRIX
from organisations.models import Collaborator, Organisation
from payments.models import Subscription, SubscriptionPlan

pytestmark = pytest.mark.django_db


def test_get_agent_profile_returns_profile(agent_user):
    assert permissions.get_agent_profile(agent_user) == agent_user.agent_profile


def test_get_agent_profile_missing(user_model):
    user = user_model.objects.create_user(
        email="no-profile@example.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    assert permissions.get_agent_profile(user) is None


def test_user_is_agent(agent_user, user_model):
    assert permissions.user_is_agent(agent_user) is True

    collaborator = user_model.objects.create_user(
        email="collab@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    assert permissions.user_is_agent(collaborator) is False


def test_user_is_collaborator(owner_user):
    assert permissions.user_is_collaborator(owner_user) is True
    assert permissions.user_is_collaborator(AnonymousUser()) is False


def test_user_is_collaborator_owner(organisations_setup, user_model):
    owner = organisations_setup["owner"]
    organisation = organisations_setup["organisation"]
    assert permissions.user_is_collaborator_owner(owner, organisation) is True

    collaborator = user_model.objects.create_user(
        email="member@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    other_org = Organisation.objects.create(name="Other Org")
    Collaborator.objects.create(
        user=collaborator,
        organisation=other_org,
        role=Collaborator.Role.MEMBER,
        job_title="Analyst",
    )
    assert permissions.user_is_collaborator_owner(collaborator, other_org) is False


def test_get_active_agent_subscription_returns_latest(agent_user, agent_subscription):
    plan = SubscriptionPlan.objects.get(code="agent-pro")
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now() - timedelta(days=30),
        current_period_end=timezone.now() - timedelta(days=1),
    )

    latest = permissions.get_active_agent_subscription(agent_user)
    assert latest == agent_subscription


def test_get_active_agent_subscription_without_profile(user_model):
    user = user_model.objects.create_user(
        email="noagent@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    assert permissions.get_active_agent_subscription(user) is None


def test_get_active_organisation_subscriptions_sorted(organisations_setup, user_model):
    owner = organisations_setup["owner"]
    organisation = organisations_setup["organisation"]
    base_subscription = organisations_setup["subscription"]

    plan = SubscriptionPlan.objects.get(code="org-pro")
    newer = Subscription.objects.create(
        organisation=organisation,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now() + timedelta(days=10),
    )

    subscriptions = permissions.get_active_organisation_subscriptions(owner)
    assert subscriptions[0] == newer
    assert subscriptions[1] == base_subscription

    outsider = user_model.objects.create_user(
        email="outsider@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    assert permissions.get_active_organisation_subscriptions(outsider) == []


def test_mapping_has_feature():
    assert permissions._mapping_has_feature({}, "missing") is False
    assert permissions._mapping_has_feature({"enabled": True}, "enabled") is True
    assert (
        permissions._mapping_has_feature({"tier": "limited"}, "tier", ("full",))
        is False
    )
    assert permissions._mapping_has_feature({"tier": "full"}, "tier", ("full",)) is True


def test_subscription_has_feature_handles_columns():
    plan = SimpleNamespace(
        features={"contract_tools": "enabled"},
        max_athletes=10,
        max_collaborators=5,
    )
    subscription = SimpleNamespace(plan=plan)

    assert permissions._subscription_has_feature(subscription, "contract_tools") is True
    assert (
        permissions._subscription_has_feature(subscription, "max_athletes", (10,))
        is True
    )
    assert (
        permissions._subscription_has_feature(subscription, "max_collaborators", (5,))
        is True
    )

    empty_plan = SimpleNamespace(
        features=None, max_athletes=None, max_collaborators=None
    )
    empty_subscription = SimpleNamespace(plan=empty_plan)
    assert (
        permissions._subscription_has_feature(empty_subscription, "contract_tools")
        is False
    )


def test_agent_has_feature_with_subscription(agent_user, agent_subscription):
    assert (
        permissions.agent_has_feature(
            agent_user, "messaging_tier", ("limited", "pro_plus")
        )
        is True
    )


def test_agent_has_feature_uses_fallback(user_model):
    user = user_model.objects.create_user(
        email="free-agent@example.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    assert permissions.agent_has_feature(user, "agent_subscription_management") is True
    assert permissions.agent_has_feature(user, "contract_tools", ("enabled",)) is False


def test_collaborator_has_feature_with_subscription(organisations_setup):
    owner = organisations_setup["owner"]
    assert (
        permissions.collaborator_has_feature(owner, "athlete_stats_scope", ("all",))
        is True
    )


def test_collaborator_has_feature_uses_fallback(user_model):
    user = user_model.objects.create_user(
        email="starter@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(name="Starter Org", owner=user)
    Collaborator.objects.create(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Manager",
    )

    assert permissions.collaborator_has_feature(user, "collaborator_invites") is True
    assert (
        permissions.collaborator_has_feature(user, "contract_tools", ("enabled",))
        is False
    )


def test_agent_meets_requirement(agent_user, agent_subscription):
    requirement = FEATURE_MATRIX["agent"]["messaging_initiate"]
    assert permissions.agent_meets_requirement(agent_user, requirement) is True


def test_collaborator_meets_requirement(organisations_setup):
    owner = organisations_setup["owner"]
    requirement = FEATURE_MATRIX["collaborator"]["athlete_stats_all"]
    assert permissions.collaborator_meets_requirement(owner, requirement) is True


def test_load_plan_features_merges_fallback():
    plan = SubscriptionPlan.objects.create(
        code="custom-plan",
        name="Custom Plan",
        price=Decimal("10.00"),
        currency="EUR",
        max_athletes=2,
        max_collaborators=4,
        features={"notification_center": False},
    )

    result = permissions._load_plan_features(
        plan.code,
        {"notification_center": True, "max_collaborators": 1},
    )

    assert result["notification_center"] is False
    assert result["max_collaborators"] == 4
    assert result["max_athletes"] == 2


def test_load_plan_features_returns_fallback_when_missing():
    fallback = {"notification_center": True}
    result = permissions._load_plan_features("unknown-plan", fallback)
    assert result == fallback
    assert result is not fallback


def test_get_agent_plan_features(agent_user, agent_subscription):
    result = permissions.get_agent_plan_features(agent_user)
    assert result["messaging_tier"] == "pro_plus"


def test_get_agent_plan_features_uses_fallback(user_model):
    user = user_model.objects.create_user(
        email="nosub@example.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    result = permissions.get_agent_plan_features(user)
    assert result["messaging_tier"] == "none"


def test_get_collaborator_plan_features_with_selection(organisations_setup):
    owner = organisations_setup["owner"]
    organisation = organisations_setup["organisation"]

    other_org = Organisation.objects.create(name="Org Pro", owner=owner)
    Collaborator.objects.create(
        user=owner,
        organisation=other_org,
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )
    plan = SubscriptionPlan.objects.get(code="org-pro")
    other_sub = Subscription.objects.create(
        organisation=other_org,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now() + timedelta(days=5),
    )

    features = permissions.get_collaborator_plan_features(owner, organisation)
    assert features["athlete_stats_scope"] == "all"

    features_selected = permissions.get_collaborator_plan_features(owner, other_org)
    assert features_selected["athlete_stats_scope"] == "all"
    assert other_sub.plan.features == features_selected


def test_get_collaborator_plan_features_uses_fallback(user_model):
    user = user_model.objects.create_user(
        email="starter-collab@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(name="Fallback Org", owner=user)
    Collaborator.objects.create(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )

    features = permissions.get_collaborator_plan_features(user)
    assert features["collaborator_invites"] is True


def test_user_feature_requirement_agent(agent_user, agent_subscription):
    requirement, granted = permissions.user_feature_requirement(
        agent_user, "messaging_initiate"
    )
    assert requirement is FEATURE_MATRIX["agent"]["messaging_initiate"]
    assert granted is True

    unknown, fallback_granted = permissions.user_feature_requirement(
        agent_user, "unknown_feature"
    )
    assert unknown is None
    assert fallback_granted is True


def test_user_feature_requirement_collaborator(organisations_setup):
    owner = organisations_setup["owner"]
    requirement, granted = permissions.user_feature_requirement(
        owner, "athlete_stats_all"
    )
    assert requirement is FEATURE_MATRIX["collaborator"]["athlete_stats_all"]
    assert granted is True


def test_user_feature_requirement_requires_authentication(user_model):
    unauthenticated = AnonymousUser()
    requirement, granted = permissions.user_feature_requirement(
        unauthenticated, "messaging_initiate"
    )
    assert requirement is None
    assert granted is False

    user = user_model.objects.create_user(
        email="support@example.com",
        password="pass1234",
    )
    requirement, granted = permissions.user_feature_requirement(
        user, "messaging_initiate"
    )
    assert requirement is FEATURE_MATRIX["agent"]["messaging_initiate"]
    assert granted is False


def test_feature_status_for_user_agent(agent_user):
    statuses = permissions.feature_status_for_user(agent_user)
    assert statuses
    assert {entry["code"] for entry in statuses} == set(
        permissions.FEATURE_MATRIX["agent"].keys()
    )


def test_feature_status_for_user_collaborator(organisations_setup):
    owner = organisations_setup["owner"]
    statuses = permissions.feature_status_for_user(owner)
    assert statuses
    assert {entry["code"] for entry in statuses} == set(
        permissions.FEATURE_MATRIX["collaborator"].keys()
    )


def test_feature_status_for_user_requires_account_type(user_model):
    unauthenticated = AnonymousUser()
    assert permissions.feature_status_for_user(unauthenticated) == []

    user = user_model.objects.create_user(
        email="unknown@example.com",
        password="pass1234",
    )
    user.account_type = "UNKNOWN"
    user.save(update_fields=["account_type"])
    assert permissions.feature_status_for_user(user) == []


def test_requirement_denied_payload():
    requirement = permissions.FeatureRequirement(
        key="contract_tools",
        label="Contract tools",
        description="Access to contract workspace",
        denied_message="Upgrade required",
        upgrade_url="https://example.com/upgrade",
        recommended_plans=("Pro", "Enterprise"),
    )
    payload = permissions.requirement_denied_payload(requirement, "Default message")
    assert payload["detail"] == "Upgrade required"
    assert payload["required_feature"] == "contract_tools"
    assert payload["recommended_plans"] == ["Pro", "Enterprise"]
