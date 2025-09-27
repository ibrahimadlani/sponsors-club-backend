from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from payments import views
from payments.models import SubscriptionPlan


def test_decimal_to_cents_rounds_half_up():
    assert views._decimal_to_cents(Decimal("10.005")) == 1001
    assert views._decimal_to_cents(Decimal("10.004")) == 1000


def test_require_stripe_secret_key_raises_when_missing(settings):
    settings.STRIPE_SECRET_KEY = ""
    with pytest.raises(views.StripeConfigurationError):
        views._require_stripe_secret_key()


def test_require_stripe_secret_key_returns_value(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_value"
    assert views._require_stripe_secret_key() == "sk_test_value"


def test_select_matching_price_prefers_currency_and_amount():
    plan = SimpleNamespace(price=Decimal("29.99"), currency="EUR")
    price_id = views._select_matching_price(
        [
            {"id": "price_usd", "currency": "usd", "unit_amount": 2999},
            {"id": "price_eur", "currency": "eur", "unit_amount_decimal": "2999"},
        ],
        plan,
    )
    assert price_id == "price_eur"


def test_to_plain_dict_handles_various_payloads():
    class Dummy:
        def __init__(self):
            self.value = 1

    class ToDict:
        def to_dict(self):
            return {"value": 2}

    assert views.to_plain_dict({"value": 3}) == {"value": 3}
    assert views.to_plain_dict(ToDict()) == {"value": 2}
    assert views.to_plain_dict(Dummy()) == {"value": 1}


def test_timestamp_to_datetime_returns_none_for_empty():
    assert views.timestamp_to_datetime(None) is None
    assert views.timestamp_to_datetime("") is None


def test_timestamp_to_datetime_parses_integer():
    timestamp = 1_700_000_000
    dt = views.timestamp_to_datetime(timestamp)
    assert dt == datetime.fromtimestamp(timestamp, tz=datetime_timezone.utc)


@pytest.mark.django_db
def test_resolve_subscription_plan_prefers_metadata_id():
    plan = SubscriptionPlan.objects.create(
        code="pro",
        name="Pro",
        price=Decimal("10.00"),
        currency="EUR",
    )
    result = views.resolve_subscription_plan({"items": {}}, {"plan_id": str(plan.id)})
    assert result == plan


@pytest.mark.django_db
def test_resolve_subscription_plan_matches_by_price_id():
    plan = SubscriptionPlan.objects.create(
        code="starter",
        name="Starter",
        price=Decimal("5.00"),
        currency="EUR",
        stripe_price_id="price_123",
    )
    data_object = {
        "items": {
            "data": [
                {
                    "price": {"id": "price_123"},
                }
            ]
        }
    }
    result = views.resolve_subscription_plan(data_object, {})
    assert result == plan
