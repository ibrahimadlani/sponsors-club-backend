"""Integration tests validating the contracts API workflow."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contracts.models import ClauseTemplate, Contract


def _create_clause_templates():
    """Create a representative subset of clause templates used in tests."""

    mandatory_data = [
        {
            "title": "Identification des parties",
            "category": ClauseTemplate.Category.ADMINISTRATIVE,
            "content": "Contrat entre {{organisation_name}} et {{athlete_name}}.",
            "placeholders": ["organisation_name", "athlete_name"],
            "is_mandatory": True,
            "version": 1,
        },
        {
            "title": "Paiement de la rémunération",
            "category": ClauseTemplate.Category.FINANCE,
            "content": "Le sponsor verse {{amount}} {{currency}} à l'athlète.",
            "placeholders": ["amount", "currency"],
            "is_mandatory": True,
            "version": 2,
        },
    ]
    optional_data = [
        {
            "title": "Présence aux événements",
            "category": ClauseTemplate.Category.OBLIGATIONS,
            "content": "L'athlète participe à {{number_of_events}} événements.",
            "placeholders": ["number_of_events"],
            "is_mandatory": False,
            "version": 1,
        }
    ]
    for payload in mandatory_data + optional_data:
        ClauseTemplate.objects.create(**payload)


def _contract_payload(organisation, agent_profile):
    """Return a default payload used when creating contracts via the API."""

    return {
        "organisation_id": str(organisation.id),
        "agent_id": str(agent_profile.id),
        "title": "Accord de sponsoring",
        "athlete_name": "Athlete Test",
        "organisation_name": organisation.name,
        "currency": "EUR",
        "total_amount": "50000.00",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    }


def _collaborator_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _agent_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _create_contract(api_client, organisation, agent_profile):
    url = reverse("contract-list")
    payload = _contract_payload(organisation, agent_profile)
    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    contract_id = response.json()["id"]
    return contract_id


@pytest.mark.django_db
def test_contract_creation_includes_mandatory_clauses(organisations_setup, agent_user):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    client = _collaborator_client(organisations_setup["owner"])

    contract_id = _create_contract(client, organisation, agent_user.agent_profile)
    contract = Contract.objects.get(id=contract_id)
    clauses = contract.clauses.order_by("position")

    assert clauses.count() == ClauseTemplate.objects.filter(is_mandatory=True).count()
    assert all(clause.is_mandatory for clause in clauses)


@pytest.mark.django_db
def test_optional_clause_addition_visible_in_contract(organisations_setup, agent_user):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    client = _collaborator_client(organisations_setup["owner"])
    contract_id = _create_contract(client, organisation, agent_user.agent_profile)

    optional_template = ClauseTemplate.objects.filter(is_mandatory=False).first()
    url = reverse("contract-add-clause", kwargs={"pk": contract_id})
    response = client.post(
        url,
        {
            "template_id": str(optional_template.id),
            "position": 5,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED

    detail_url = reverse("contract-detail", kwargs={"pk": contract_id})
    detail_response = client.get(detail_url)
    assert detail_response.status_code == status.HTTP_200_OK
    clause_ids = {clause["id"] for clause in detail_response.json()["clauses"]}
    assert str(response.json()["id"]) in clause_ids


@pytest.mark.django_db
def test_agent_proposes_revision(organisations_setup, agent_user):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    collaborator_client = _collaborator_client(organisations_setup["owner"])
    contract_id = _create_contract(collaborator_client, organisation, agent_user.agent_profile)
    contract = Contract.objects.get(id=contract_id)

    clause = contract.clauses.first()
    agent_client = _agent_client(agent_user)
    url = reverse("contract-revisions", kwargs={"pk": contract_id})
    response = agent_client.post(
        url,
        {"clauses": [str(clause.id)], "comment": "Proposition de modification"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    contract.refresh_from_db()
    assert contract.revisions.count() == 1


@pytest.mark.django_db
def test_owner_can_advance_contract_to_agreement(organisations_setup, agent_user):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    client = _collaborator_client(organisations_setup["owner"])
    contract_id = _create_contract(client, organisation, agent_user.agent_profile)

    status_url = reverse("contract-update-status", kwargs={"pk": contract_id})
    negotiation_response = client.patch(status_url, {"status": "negotiation"}, format="json")
    assert negotiation_response.status_code == status.HTTP_200_OK
    agreement_response = client.patch(status_url, {"status": "agreement"}, format="json")
    assert agreement_response.status_code == status.HTTP_200_OK
    assert agreement_response.json()["status"] == "agreement"


@pytest.mark.django_db
def test_member_cannot_validate_contract(organisations_setup, agent_user, user_model):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    owner_client = _collaborator_client(organisations_setup["owner"])
    contract_id = _create_contract(owner_client, organisation, agent_user.agent_profile)

    member_user = user_model.objects.create_user(
        email="member@test.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    Collaborator = organisation.collaborators.model
    Collaborator.objects.create(
        organisation=organisation,
        user=member_user,
        role=Collaborator.Role.MEMBER,
        job_title="Manager",
    )
    member_client = _collaborator_client(member_user)
    status_url = reverse("contract-update-status", kwargs={"pk": contract_id})
    response = member_client.patch(status_url, {"status": "negotiation"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_contract_export_returns_pdf(organisations_setup, agent_user):
    _create_clause_templates()
    organisation = organisations_setup["organisation"]
    client = _collaborator_client(organisations_setup["owner"])
    contract_id = _create_contract(client, organisation, agent_user.agent_profile)

    export_url = reverse("contract-export", kwargs={"pk": contract_id})
    response = client.get(export_url)
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
