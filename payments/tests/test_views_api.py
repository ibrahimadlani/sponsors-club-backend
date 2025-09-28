from __future__ import annotations

import uuid
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from organisations.models import Collaborator, Organisation
from payments import views
from payments.models import Subscription, SubscriptionPlan


def create_plan(*, code: str | None = None, price: Decimal | None = None, features: dict | None = None, **overrides) -> SubscriptionPlan:
    """Create a subscription plan tailored for tests."""

    if code is None:
        code = f"plan-{uuid.uuid4().hex[:8]}"
    if price is None:
        price = Decimal("10.00")
    base_features = {"tier": "agent", "agent_subscription_management": True}
    if features is not None:
        base_features.update(features)
    defaults = {
        "code": code,
        "name": f"Test {code}",
        "price": price,
        "currency": "EUR",
        "max_athletes": 1,
        "max_collaborators": 0,
        "features": base_features,
    }
    defaults.update(overrides)
    return SubscriptionPlan.objects.create(**defaults)


@pytest.mark.django_db
def test_plan_list_view_returns_active_plans_sorted(api_client):
    cheaper = create_plan(price=Decimal("5.00"))
    expensive = create_plan(price=Decimal("25.00"))
    create_plan(price=Decimal("50.00"), is_active=False)

    response = api_client.get(reverse("payments-plans"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    prices = [Decimal(item["price"]) for item in payload]
    assert prices == sorted(prices)

    identifiers = {item["id"] for item in payload}
    expected_ids = {str(cheaper.id), str(expensive.id)}
    assert expected_ids.issubset(identifiers)

    subset = [item for item in payload if item["id"] in expected_ids]
    assert len(subset) == 2
    assert subset[0]["id"] == str(cheaper.id)


@pytest.mark.django_db
def test_checkout_session_returns_service_unavailable_when_configuration_missing(
    api_client, agent_user, monkeypatch
):
    plan = create_plan()

    def raise_config_error(_plan):
        raise views.StripeConfigurationError("Stripe integration is not configured.")

    monkeypatch.setattr("payments.views.ensure_plan_price_id", raise_config_error)

    api_client.force_authenticate(agent_user)
    response = api_client.post(
        reverse("payments-stripe-checkout"),
        {
            "plan_id": str(plan.id),
            "agent_id": str(agent_user.agent_profile.id),
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Stripe integration" in response.json()["detail"]


@pytest.mark.django_db
def test_checkout_session_returns_bad_request_when_plan_invalid(
    api_client, agent_user, monkeypatch
):
    plan = create_plan()

    def raise_plan_error(_plan):
        raise views.StripePlanConfigurationError("Plan misconfigured")

    monkeypatch.setattr("payments.views.ensure_plan_price_id", raise_plan_error)

    api_client.force_authenticate(agent_user)
    response = api_client.post(
        reverse("payments-stripe-checkout"),
        {
            "plan_id": str(plan.id),
            "agent_id": str(agent_user.agent_profile.id),
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Plan misconfigured"


@pytest.mark.django_db
def test_checkout_session_creates_stripe_session_with_metadata(
    api_client, agent_user, monkeypatch, settings
):
    settings.STRIPE_SECRET_KEY = "sk_test_value"
    settings.STRIPE_PUBLIC_KEY = "pk_test_value"
    plan = create_plan()

    monkeypatch.setattr("payments.views.ensure_plan_price_id", lambda _plan: "price_123")
    monkeypatch.setattr("payments.views._require_stripe_secret_key", lambda: "sk_test_value")

    captured: dict[str, dict] = {}

    def fake_session_create(**payload):
        captured["payload"] = payload
        return {"id": "cs_test_123", "url": "https://stripe.test/session"}

    monkeypatch.setattr(
        "payments.views.stripe.checkout.Session.create",
        fake_session_create,
    )

    api_client.force_authenticate(agent_user)
    response = api_client.post(
        reverse("payments-stripe-checkout"),
        {
            "plan_id": str(plan.id),
            "agent_id": str(agent_user.agent_profile.id),
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == "cs_test_123"
    assert body["url"].startswith("https://stripe.test/")
    assert body["stripe_public_key"] == "pk_test_value"
    metadata = captured["payload"]["metadata"]
    assert metadata["plan_id"] == str(plan.id)
    assert metadata["scope"] == "agent"
    assert metadata["scope_id"] == str(agent_user.agent_profile.id)


@pytest.mark.django_db
def test_my_subscription_view_returns_agent_subscription(api_client, agent_user):
    plan = create_plan()
    organisation_plan = create_plan(features={"tier": "organisation", "organisation_subscription_management": True})
    organisation = Organisation.objects.create(name="Org", owner=agent_user)
    Collaborator.objects.create(
        user=agent_user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )
    Subscription.objects.create(
        organisation=organisation,
        plan=organisation_plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )

    api_client.force_authenticate(agent_user)
    response = api_client.get(reverse("payments-subscription-me"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["agent"] == str(agent_user.agent_profile.id)


@pytest.mark.django_db
def test_my_subscription_view_returns_org_subscription_when_agent_absent(api_client):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="collaborator@test.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(name="Org B", owner=user)
    Collaborator.objects.create(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )
    plan = create_plan(
        features={"tier": "organisation", "organisation_subscription_management": True}
    )
    Subscription.objects.create(
        organisation=organisation,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )

    api_client.force_authenticate(user)
    response = api_client.get(reverse("payments-subscription-me"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["organisation"] == str(organisation.id)


@pytest.mark.django_db
def test_my_subscription_view_returns_not_found_when_missing(api_client, agent_user):
    api_client.force_authenticate(agent_user)
    response = api_client.get(reverse("payments-subscription-me"))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_my_subscription_delete_cancels_subscription(api_client, agent_user):
    plan = create_plan()
    subscription = Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )

    api_client.force_authenticate(agent_user)
    response = api_client.delete(reverse("payments-subscription-me"))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.CANCELED


@pytest.mark.django_db
def test_my_subscription_delete_returns_not_found_when_no_subscription(api_client, agent_user):
    api_client.force_authenticate(agent_user)
    response = api_client.delete(reverse("payments-subscription-me"))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_webhook_rejects_events_without_type(api_client):
    response = api_client.post(reverse("payments-stripe-webhook"), {"data": {}}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Event type missing."


@pytest.mark.django_db
def test_webhook_subscription_event_requires_payload(api_client):
    response = api_client.post(
        reverse("payments-stripe-webhook"),
        {"type": "customer.subscription.updated", "data": {}},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Subscription data missing."


@pytest.mark.django_db
def test_webhook_checkout_session_syncs_subscription(
    api_client, agent_user, settings, monkeypatch
):
    settings.STRIPE_SECRET_KEY = "sk_test_value"
    plan = create_plan()
    metadata = {
        "plan_id": str(plan.id),
        "plan_code": plan.code,
        "scope": "agent",
        "scope_id": str(agent_user.agent_profile.id),
    }
    now = int(datetime.now(tz=datetime_timezone.utc).timestamp())
    subscription_payload = {
        "id": "sub_123",
        "status": Subscription.Status.ACTIVE,
        "current_period_start": now,
        "current_period_end": now + 3600,
        "customer": "cus_123",
    }

    monkeypatch.setattr(
        "payments.views.stripe.Subscription.retrieve",
        lambda subscription_id: subscription_payload,
    )

    response = api_client.post(
        reverse("payments-stripe-webhook"),
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {"subscription": "sub_123", "metadata": metadata},
            },
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    subscription = Subscription.objects.get(stripe_subscription_id="sub_123")
    assert subscription.agent_id == agent_user.agent_profile.id
    assert subscription.plan_id == plan.id


@pytest.mark.django_db
def test_sync_subscription_from_payload_returns_none_when_plan_missing():
    assert (
        views.sync_subscription_from_payload(
            {"id": "sub_missing", "status": "active"}, {"plan_id": uuid.uuid4()}
        )
        is None
    )


@pytest.mark.django_db
def test_sync_subscription_from_payload_creates_org_subscription():
    plan = create_plan(features={"tier": "organisation", "organisation_subscription_management": True})
    organisation = Organisation.objects.create(name="Webhook Org")
    now = int(datetime.now(tz=datetime_timezone.utc).timestamp())
    subscription = views.sync_subscription_from_payload(
        {
            "id": "sub_org",
            "status": Subscription.Status.ACTIVE,
            "current_period_start": now,
            "current_period_end": now + 3600,
            "customer": "cus_org",
        },
        {
            "plan_id": str(plan.id),
            "scope": "organisation",
            "scope_id": str(organisation.id),
        },
    )

    assert subscription is not None
    assert subscription.organisation_id == organisation.id
    assert subscription.plan_id == plan.id


@pytest.mark.django_db
def test_sync_subscription_from_payload_updates_existing_subscription(agent_user):
    initial_plan = create_plan()
    updated_plan = create_plan()
    subscription = Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=initial_plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
        stripe_customer_id="cus_original",
        stripe_subscription_id="sub_existing",
    )

    now = int(datetime.now(tz=datetime_timezone.utc).timestamp())
    views.sync_subscription_from_payload(
        {
            "id": "sub_existing",
            "status": Subscription.Status.PAST_DUE,
            "current_period_start": now,
            "current_period_end": now + 7200,
            "customer": "cus_updated",
        },
        {
            "plan_id": str(updated_plan.id),
            "scope": "agent",
            "scope_id": str(agent_user.agent_profile.id),
        },
    )

    subscription.refresh_from_db()
    assert subscription.plan_id == updated_plan.id
    assert subscription.status == Subscription.Status.PAST_DUE
    assert subscription.stripe_customer_id == "cus_updated"

