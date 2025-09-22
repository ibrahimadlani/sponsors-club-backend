"""Integration tests covering Stripe checkout and webhook flows."""

import json
from datetime import datetime, timedelta, timezone as datetime_timezone

import pytest
from django.urls import reverse
from django.utils import timezone

import stripe

from payments.models import Subscription, SubscriptionPlan


@pytest.mark.django_db
def test_checkout_session_creation_sets_metadata(
    api_client, agent_user, settings, monkeypatch
):
    """Checkout session creation should call Stripe with scope metadata.

    Args:
        api_client (APIClient): Authenticated test client hitting the API.
        agent_user (User): Agent user initiating the checkout.
        settings (Settings): Django settings object for runtime configuration.
        monkeypatch (MonkeyPatch): Pytest helper for faking Stripe calls.
    """

    settings.STRIPE_PUBLIC_KEY = "pk_test_dummy"
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"

    plan = SubscriptionPlan.objects.get(code="agent-pro")
    plan.stripe_product_id = "prod_test_123"
    plan.stripe_price_id = ""
    plan.save(update_fields=["stripe_product_id", "stripe_price_id", "updated_at"])

    captured_payload = {}

    class DummyPriceList:
        def __init__(self):
            self.data = [
                type(
                    "Price",
                    (),
                    {"id": "price_123", "currency": "eur", "unit_amount": 5000},
                )()
            ]

    def fake_price_list(**kwargs):
        captured_payload["price_list_kwargs"] = kwargs
        return DummyPriceList()

    def fake_session_create(**kwargs):
        captured_payload["session_kwargs"] = kwargs
        return {"id": "cs_test_123", "url": "https://stripe.test/checkout/cs_test_123"}

    def fake_product_retrieve(product_id):
        assert product_id == "prod_test_123"
        return {"id": product_id}

    monkeypatch.setattr(stripe.Product, "retrieve", fake_product_retrieve)
    monkeypatch.setattr(stripe.Price, "list", fake_price_list)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    client = api_client
    client.force_authenticate(user=agent_user)

    payload = {
        "plan_id": str(plan.id),
        "agent_id": str(agent_user.agent_profile.id),
        "success_url": "https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://example.com/cancel",
    }

    response = client.post(
        reverse("payments-stripe-checkout"),
        data=payload,
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "cs_test_123"
    assert body["url"] == "https://stripe.test/checkout/cs_test_123"
    assert body["stripe_public_key"] == "pk_test_dummy"

    plan.refresh_from_db()
    assert plan.stripe_price_id == "price_123"

    price_kwargs = captured_payload["price_list_kwargs"]
    assert price_kwargs["product"] == "prod_test_123"
    assert price_kwargs["type"] == "recurring"
    assert price_kwargs["limit"] == 10

    session_kwargs = captured_payload["session_kwargs"]
    metadata = session_kwargs["metadata"]
    assert metadata["plan_id"] == str(plan.id)
    assert metadata["scope"] == "agent"
    assert metadata["scope_id"] == str(agent_user.agent_profile.id)
    assert session_kwargs["line_items"][0]["price"] == "price_123"
    assert session_kwargs["subscription_data"]["metadata"]["plan_code"] == plan.code


@pytest.mark.django_db
def test_checkout_session_creation_creates_missing_price(
    api_client, agent_user, settings, monkeypatch
):
    """When no matching price exists, the integration should create one automatically.

    Args:
        api_client (APIClient): Authenticated test client hitting the API.
        agent_user (User): Agent initiating checkout for their own profile.
        settings (Settings): Django settings object for runtime configuration.
        monkeypatch (MonkeyPatch): Pytest helper for mocking Stripe endpoints.
    """

    settings.STRIPE_PUBLIC_KEY = "pk_test_dummy"
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"

    plan = SubscriptionPlan.objects.get(code="agent-pro")
    plan.stripe_product_id = "prod_test_123"
    plan.stripe_price_id = ""
    plan.save(update_fields=["stripe_product_id", "stripe_price_id", "updated_at"])

    captured = {}

    class DummyPriceList:
        def __init__(self):
            self.data = []

    def fake_product_retrieve(product_id):
        assert product_id == "prod_test_123"
        return {"id": product_id}

    def fake_price_list(**kwargs):
        captured["price_list_kwargs"] = kwargs
        return DummyPriceList()

    def fake_price_create(**kwargs):
        captured["price_create_kwargs"] = kwargs
        return {"id": "price_created"}

    def fake_session_create(**kwargs):
        captured["session_kwargs"] = kwargs
        return {"id": "cs_test_456", "url": "https://stripe.test/cs_test_456"}

    monkeypatch.setattr(stripe.Product, "retrieve", fake_product_retrieve)
    monkeypatch.setattr(stripe.Price, "list", fake_price_list)
    monkeypatch.setattr(stripe.Price, "create", fake_price_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    client = api_client
    client.force_authenticate(user=agent_user)

    payload = {
        "plan_id": str(plan.id),
        "agent_id": str(agent_user.agent_profile.id),
        "success_url": "https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://example.com/cancel",
    }

    response = client.post(
        reverse("payments-stripe-checkout"),
        data=payload,
        format="json",
    )

    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.stripe_price_id == "price_created"

    assert captured["price_create_kwargs"]["product"] == "prod_test_123"
    assert captured["price_create_kwargs"]["currency"] == "eur"
    assert captured["price_create_kwargs"]["unit_amount"] == 5000


@pytest.mark.django_db
def test_checkout_session_creation_recovers_from_missing_product(
    api_client, agent_user, settings, monkeypatch
):
    """If the configured product is missing, it should be recreated automatically.

    Args:
        api_client (APIClient): Authenticated test client hitting the API.
        agent_user (User): Agent user performing the checkout call.
        settings (Settings): Django settings object updated for Stripe keys.
        monkeypatch (MonkeyPatch): Pytest helper for overriding Stripe SDK calls.
    """

    settings.STRIPE_PUBLIC_KEY = "pk_test_dummy"
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"

    plan = SubscriptionPlan.objects.get(code="agent-pro")
    plan.stripe_product_id = "prod_missing"
    plan.stripe_price_id = ""
    plan.save(update_fields=["stripe_product_id", "stripe_price_id", "updated_at"])

    captured = {}

    class DummyPriceList:
        def __init__(self):
            self.data = []

    def fake_product_retrieve(product_id):
        raise stripe.error.InvalidRequestError(
            message="No such product",
            param="product",
            code="resource_missing",
            http_body="",
            http_status=404,
            json_body=None,
            headers={},
        )

    def fake_product_create(**kwargs):
        captured["product_create_kwargs"] = kwargs
        return {"id": "prod_new"}

    def fake_price_list(**kwargs):
        captured["price_list_kwargs"] = kwargs
        return DummyPriceList()

    def fake_price_create(**kwargs):
        captured["price_create_kwargs"] = kwargs
        return {"id": "price_new"}

    def fake_session_create(**kwargs):
        captured["session_kwargs"] = kwargs
        return {"id": "cs_test_789", "url": "https://stripe.test/cs_test_789"}

    monkeypatch.setattr(stripe.Product, "retrieve", fake_product_retrieve)
    monkeypatch.setattr(stripe.Product, "create", fake_product_create)
    monkeypatch.setattr(stripe.Price, "list", fake_price_list)
    monkeypatch.setattr(stripe.Price, "create", fake_price_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    client = api_client
    client.force_authenticate(user=agent_user)

    payload = {
        "plan_id": str(plan.id),
        "agent_id": str(agent_user.agent_profile.id),
        "success_url": "https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://example.com/cancel",
    }

    response = client.post(
        reverse("payments-stripe-checkout"),
        data=payload,
        format="json",
    )

    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.stripe_product_id == "prod_new"
    assert plan.stripe_price_id == "price_new"

    assert captured["product_create_kwargs"]["name"] == plan.name
    assert captured["price_create_kwargs"]["product"] == "prod_new"


@pytest.mark.django_db
def test_webhook_synchronises_subscription(
    api_client, agent_user, settings, monkeypatch
):
    """Webhook subscription events should create or update local records."""

    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

    plan = SubscriptionPlan.objects.get(code="agent-pro")
    plan.stripe_product_id = "prod_test_123"
    plan.stripe_price_id = "price_123"
    plan.save(update_fields=["stripe_product_id", "stripe_price_id", "updated_at"])

    now = timezone.now()
    period_end = now + timedelta(days=30)

    subscription_payload = {
        "id": "sub_123",
        "status": "active",
        "current_period_start": int(now.timestamp()),
        "current_period_end": int(period_end.timestamp()),
        "customer": "cus_123",
        "metadata": {
            "plan_id": str(plan.id),
            "scope": "agent",
            "scope_id": str(agent_user.agent_profile.id),
        },
        "items": {
            "data": [
                {"price": {"id": plan.stripe_price_id}},
            ]
        },
    }

    event_payload = {
        "type": "customer.subscription.updated",
        "data": {"object": subscription_payload},
    }

    def fake_construct_event(payload, sig_header, secret):
        assert secret == "whsec_test"
        assert sig_header == "t=123,v1=test"
        assert json.loads(payload.decode("utf-8")) == event_payload
        return event_payload

    monkeypatch.setattr(
        stripe.Webhook, "construct_event", staticmethod(fake_construct_event)
    )

    response = api_client.post(
        reverse("payments-stripe-webhook"),
        data=json.dumps(event_payload),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="t=123,v1=test",
    )

    assert response.status_code == 200

    subscription = Subscription.objects.get(stripe_subscription_id="sub_123")
    assert subscription.agent_id == agent_user.agent_profile.id
    assert subscription.plan_id == plan.id
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.stripe_customer_id == "cus_123"
    expected_end = datetime.fromtimestamp(
        subscription_payload["current_period_end"], tz=datetime_timezone.utc
    )
    assert subscription.current_period_end == expected_end


@pytest.mark.django_db
def test_checkout_session_fails_without_stripe_secret_key(
    api_client, agent_user, settings
):
    """Missing Stripe configuration should return a service unavailable error."""

    settings.STRIPE_PUBLIC_KEY = "pk_test_dummy"
    settings.STRIPE_SECRET_KEY = ""

    plan = SubscriptionPlan.objects.get(code="agent-pro")
    plan.stripe_product_id = "prod_test_123"
    plan.stripe_price_id = ""
    plan.save(update_fields=["stripe_product_id", "stripe_price_id", "updated_at"])

    client = api_client
    client.force_authenticate(user=agent_user)

    payload = {
        "plan_id": str(plan.id),
        "agent_id": str(agent_user.agent_profile.id),
        "success_url": "https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://example.com/cancel",
    }

    response = client.post(
        reverse("payments-stripe-checkout"),
        data=payload,
        format="json",
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Stripe integration is not configured. Please contact support."
    )
