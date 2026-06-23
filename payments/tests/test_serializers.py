from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.feature_matrix import COLLABORATOR_FEATURES
from core.permissions import requirement_denied_payload
from organisations.models import Collaborator, Organisation
from payments.models import Subscription, SubscriptionPlan
from payments.serializers import (
    StripeCheckoutSessionSerializer,
    SubscriptionCreateSerializer,
)
from users.models import AgentProfile


@pytest.fixture
def organisation_owner(user_model, db):
    user = user_model.objects.create_user(
        email="owner@example.com",
        password="pass1234",
        first_name="Org",
        last_name="Owner",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(name="Acme", owner=user)
    collaborator = Collaborator.objects.create(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    return user, organisation, collaborator


@pytest.fixture
def subscription_plan(db):
    return SubscriptionPlan.objects.create(
        code="custom-plan",
        name="Custom Plan",
        price="49.99",
        currency="EUR",
        max_athletes=10,
        max_collaborators=5,
        features={"organisation_subscription_management": True},
        is_active=True,
    )


def build_request(user, data):
    return SimpleNamespace(user=user, data=data)


@pytest.mark.django_db
def test_subscription_create_serializer_creates_subscription_for_organisation(
    subscription_plan, organisation_owner, monkeypatch
):
    user, organisation, _ = organisation_owner
    monkeypatch.setattr(
        "payments.serializers.collaborator_meets_requirement", lambda *_: True
    )
    request = build_request(
        user,
        {
            "start_at": "2024-01-01T12:00:00",
            "current_period_end": "2024-02-01T12:00:00",
        },
    )
    serializer = SubscriptionCreateSerializer(
        data={
            "plan_id": subscription_plan.id,
            "organisation_id": organisation.id,
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_456",
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    subscription = serializer.save()

    assert subscription.plan == subscription_plan
    assert subscription.organisation == organisation
    assert subscription.agent is None
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.stripe_customer_id == "cus_123"
    assert subscription.stripe_subscription_id == "sub_456"
    assert subscription.start_at.tzinfo == datetime_timezone.utc
    assert subscription.current_period_end.tzinfo == datetime_timezone.utc


@pytest.mark.django_db
def test_subscription_create_serializer_blocks_unentitled_collaborator(
    subscription_plan, organisation_owner, monkeypatch
):
    user, organisation, _ = organisation_owner
    monkeypatch.setattr(
        "payments.serializers.collaborator_meets_requirement", lambda *_: False
    )
    request = build_request(user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "organisation_id": organisation.id},
        context={"request": request},
    )

    with pytest.raises(PermissionDenied) as exc:
        serializer.is_valid(raise_exception=True)

    requirement = COLLABORATOR_FEATURES["organisation_subscription_management"]
    detail = exc.value.detail

    # Django REST framework wraps permission payloads in ``ErrorDetail`` objects
    # when they come from :class:`PermissionDenied`. Rather than compare the
    # entire structure (which can change across DRF releases), assert that the
    # fields we care about survived the round-trip intact.
    expected_payload = requirement_denied_payload(
        requirement, "Upgrade required to manage organisation subscriptions."
    )

    for key in ("required_feature", "allowed_values", "upgrade_url"):
        actual = detail[key]
        expected = expected_payload[key]
        if isinstance(actual, list):
            actual = [str(item) for item in actual]
            expected = [str(item) for item in expected]
        elif hasattr(actual, "code"):
            actual = str(actual)
            expected = str(expected)
        assert actual == expected

    assert [str(item) for item in detail["recommended_plans"]] == [
        str(item) for item in expected_payload["recommended_plans"]
    ]
    assert str(detail["detail"]) == expected_payload["detail"]


@pytest.mark.django_db
def test_subscription_create_serializer_prevents_duplicate_organisation_subscription(
    subscription_plan, organisation_owner, monkeypatch
):
    user, organisation, _ = organisation_owner
    monkeypatch.setattr(
        "payments.serializers.collaborator_meets_requirement", lambda *_: True
    )
    Subscription.objects.create(
        organisation=organisation,
        plan=subscription_plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )
    request = build_request(user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "organisation_id": organisation.id},
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    assert "Organisation already has an active subscription." in str(exc.value.detail)


@pytest.mark.django_db
def test_subscription_create_serializer_validates_agent_scope(
    subscription_plan, user_model, monkeypatch
):
    agent_user = user_model.objects.create_user(
        email="agent@example.com",
        password="pass1234",
        first_name="Agent",
        last_name="User",
        account_type=user_model.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)

    request = build_request(
        agent_user,
        {
            "current_period_start": "2024-05-01T08:00:00Z",
        },
    )
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "agent_id": agent_profile.id},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    subscription = serializer.save()

    assert subscription.agent == agent_profile
    assert subscription.organisation is None
    assert subscription.start_at == datetime(
        2024, 5, 1, 8, 0, tzinfo=datetime_timezone.utc
    )
    assert subscription.current_period_end.tzinfo is not None


@pytest.mark.django_db
def test_subscription_create_serializer_rejects_foreign_agent(
    subscription_plan, user_model
):
    owner = user_model.objects.create_user(
        email="owner2@example.com",
        password="pass1234",
        first_name="Owner",
        last_name="User",
        account_type=user_model.AccountType.AGENT,
    )
    agent_user = user_model.objects.create_user(
        email="agent2@example.com",
        password="pass1234",
        first_name="Agent",
        last_name="Two",
        account_type=user_model.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)

    request = build_request(owner, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "agent_id": agent_profile.id},
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    assert "You can only subscribe for your own agent profile." in str(exc.value.detail)


@pytest.mark.django_db
def test_subscription_create_serializer_allows_staff_to_manage_foreign_agent(
    subscription_plan, user_model, monkeypatch
):
    agent_user = user_model.objects.create_user(
        email="managed@example.com",
        password="pass1234",
        first_name="Managed",
        last_name="Agent",
        account_type=user_model.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)

    staff_user = user_model.objects.create_user(
        email="staff@example.com",
        password="pass1234",
        first_name="Staff",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])

    fixed_now = timezone.make_aware(datetime(2024, 3, 15, 9, 30))
    monkeypatch.setattr("payments.serializers.timezone.now", lambda: fixed_now)

    request = build_request(staff_user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "agent_id": agent_profile.id},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    subscription = serializer.save()

    assert subscription.agent == agent_profile
    assert subscription.start_at == fixed_now
    assert subscription.current_period_end == fixed_now


@pytest.mark.django_db
def test_subscription_create_serializer_requires_scope_selection(
    subscription_plan, organisation_owner
):
    user, _, _ = organisation_owner
    request = build_request(user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id},
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    assert "An organisation_id or agent_id is required." in str(exc.value.detail)


@pytest.mark.django_db
def test_subscription_create_serializer_rejects_multiple_scopes(
    subscription_plan, organisation_owner
):
    user, organisation, _ = organisation_owner
    agent_profile = AgentProfile.objects.create(user=user)
    request = build_request(user, {})
    serializer = SubscriptionCreateSerializer(
        data={
            "plan_id": subscription_plan.id,
            "organisation_id": organisation.id,
            "agent_id": agent_profile.id,
        },
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    assert "Provide either organisation_id or agent_id, not both." in str(
        exc.value.detail
    )


@pytest.mark.django_db
def test_subscription_create_serializer_rejects_inactive_plan(organisation_owner):
    inactive_plan = SubscriptionPlan.objects.create(
        code="inactive-plan",
        name="Inactive",
        price="10.00",
        currency="EUR",
        is_active=False,
    )
    user, organisation, _ = organisation_owner
    request = build_request(user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": inactive_plan.id, "organisation_id": organisation.id},
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    detail = exc.value.detail
    assert "plan_id" in detail
    error = detail["plan_id"][0]
    assert getattr(error, "code", "") == "invalid"
    assert str(error) == "Plan not found or inactive."


@pytest.mark.django_db
def test_subscription_create_serializer_rejects_missing_agent(
    subscription_plan, user_model
):
    agent_user = user_model.objects.create_user(
        email="agent3@example.com",
        password="pass1234",
        first_name="Agent",
        last_name="Three",
        account_type=user_model.AccountType.AGENT,
    )
    request = build_request(agent_user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "agent_id": uuid4()},
        context={"request": request},
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.is_valid(raise_exception=True)

    detail = exc.value.detail
    assert "agent_id" in detail
    error = detail["agent_id"][0]
    assert getattr(error, "code", "") == "invalid"
    assert str(error) == "Agent not found."


@pytest.mark.django_db
def test_subscription_create_serializer_update_not_supported(
    subscription_plan, user_model
):
    agent_user = user_model.objects.create_user(
        email="agent4@example.com",
        password="pass1234",
        first_name="Agent",
        last_name="Four",
        account_type=user_model.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)
    request = build_request(agent_user, {})
    serializer = SubscriptionCreateSerializer(
        data={"plan_id": subscription_plan.id, "agent_id": agent_profile.id},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    subscription = serializer.save()

    with pytest.raises(NotImplementedError):
        serializer.update(subscription, {})


@pytest.mark.django_db
def test_stripe_checkout_session_serializer_reuses_subscription_validation(
    subscription_plan, user_model
):
    agent_user = user_model.objects.create_user(
        email="agent5@example.com",
        password="pass1234",
        first_name="Agent",
        last_name="Five",
        account_type=user_model.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)

    request = build_request(agent_user, {})
    serializer = StripeCheckoutSessionSerializer(
        data={
            "plan_id": subscription_plan.id,
            "agent_id": agent_profile.id,
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["plan"] == subscription_plan
    assert serializer.validated_data["agent_profile"] == agent_profile
    assert serializer.validated_data["organisation"] is None
