"""Integration tests for contract API behaviour."""

from datetime import date

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import Athlete, Sport


@pytest.fixture
def contract_client(owner_user):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def contract_sport():
    return Sport.objects.create(name="Rugby", discipline="Team Sport")


@pytest.fixture
def contract_athlete(agent_user, contract_sport):
    return Athlete.objects.create(
        sport=contract_sport,
        agent=agent_user.agent_profile,
        full_name="Contract Athlete",
        birth_date=date(1995, 5, 5),
        nationality="FR",
        is_self_represented=False,
    )


@pytest.mark.django_db
def test_contract_create_success(
    contract_client, organisations_setup, contract_athlete
):
    organisation = organisations_setup["organisation"]
    url = reverse("contract-list")
    payload = {
        "organisation_id": str(organisation.id),
        "athlete_id": str(contract_athlete.id),
        "currency": "EUR",
        "amount": "10000.00",
    }
    response = contract_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_contract_create_denied_without_feature(
    contract_client,
    organisations_setup,
    contract_athlete,
):
    organisation = organisations_setup["organisation"]
    subscription = organisation.subscriptions.first()
    plan = subscription.plan
    plan.features["contract_tools"] = "disabled"
    plan.save(update_fields=["features"])

    url = reverse("contract-list")
    payload = {
        "organisation_id": str(organisation.id),
        "athlete_id": str(contract_athlete.id),
        "currency": "EUR",
        "amount": "10000.00",
    }
    response = contract_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "contract_tools"
