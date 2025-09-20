from __future__ import annotations

from datetime import date

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contracts.data import CLAUSE_TEMPLATE_FIXTURES
from contracts.models import ClauseTemplate, Contract, ContractFile, ContractRevision
from organisations.models import Collaborator


@pytest.fixture
def collaborator_client(owner_user):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def agent_client(agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    return client


@pytest.fixture
def clause_templates():
    templates = []
    for fixture in CLAUSE_TEMPLATE_FIXTURES:
        template, _ = ClauseTemplate.objects.get_or_create(
            id=fixture["uuid"],
            defaults={
                "category": fixture["category"],
                "title": fixture["title"],
                "content": fixture["content"],
                "placeholders": fixture["placeholders"],
                "is_mandatory": fixture["is_mandatory"],
                "version": fixture["version"],
            },
        )
        templates.append(template)
    return templates


@pytest.fixture
def contract_payload(organisations_setup, agent_user):
    organisation = organisations_setup["organisation"]
    payload = {
        "title": "Sponsorship Agreement",
        "organisation_id": str(organisation.id),
        "agent_id": str(agent_user.agent_profile.id),
        "effective_date": date(2024, 1, 1),
        "expiration_date": date(2024, 12, 31),
    }
    return payload


@pytest.mark.django_db
def test_contract_creation_includes_mandatory_clauses(
    collaborator_client, clause_templates, contract_payload
):
    url = reverse("contract-list")
    response = collaborator_client.post(url, contract_payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    mandatory_count = ClauseTemplate.objects.filter(is_mandatory=True).count()
    assert len(data["clauses"]) == mandatory_count
    mandatory_titles = set(
        ClauseTemplate.objects.filter(is_mandatory=True).values_list("title", flat=True)
    )
    clause_titles = {clause["title"] for clause in data["clauses"]}
    assert mandatory_titles.issubset(clause_titles)


@pytest.mark.django_db
def test_optional_clause_visible_in_contract_detail(
    collaborator_client, clause_templates, contract_payload
):
    contract_id = collaborator_client.post(
        reverse("contract-list"), contract_payload, format="json"
    ).json()["id"]
    optional_template = ClauseTemplate.objects.filter(is_mandatory=False).first()
    assert optional_template is not None

    add_clause_url = reverse("contract-add-clause", args=[contract_id])
    payload = {
        "template_id": str(optional_template.id),
        "content": optional_template.content,
    }
    add_response = collaborator_client.post(add_clause_url, payload, format="json")
    assert add_response.status_code == status.HTTP_201_CREATED

    detail_response = collaborator_client.get(reverse("contract-detail", args=[contract_id]))
    assert detail_response.status_code == status.HTTP_200_OK
    detail_data = detail_response.json()
    assert any(
        clause["title"] == optional_template.title for clause in detail_data["clauses"]
    )


@pytest.mark.django_db
def test_agent_proposes_revision(
    collaborator_client, agent_client, clause_templates, contract_payload
):
    contract_id = collaborator_client.post(
        reverse("contract-list"), contract_payload, format="json"
    ).json()["id"]
    contract = Contract.objects.get(id=contract_id)
    clause = contract.clauses.first()
    assert clause is not None

    revisions_url = reverse("contract-revisions", args=[contract_id])
    payload = {"clause_ids": [str(clause.id)], "comment": "Need to adjust payment schedule."}
    response = agent_client.post(revisions_url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert ContractRevision.objects.filter(contract=contract).count() == 1
    contract.refresh_from_db()
    assert contract.status == Contract.Status.NEGOTIATION


@pytest.fixture
def member_user(user_model, organisations_setup):
    organisation = organisations_setup["organisation"]
    user = user_model.objects.create_user(
        email="member@test.com",
        password="pass1234",
        first_name="Member",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    Collaborator.objects.create(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Manager",
    )
    return user


@pytest.fixture
def member_client(member_user):
    client = APIClient()
    client.force_authenticate(user=member_user)
    return client


@pytest.mark.django_db
def test_owner_can_progress_to_agreement(
    collaborator_client, agent_client, clause_templates, contract_payload
):
    contract_id = collaborator_client.post(
        reverse("contract-list"), contract_payload, format="json"
    ).json()["id"]
    contract = Contract.objects.get(id=contract_id)
    clause = contract.clauses.first()
    revisions_url = reverse("contract-revisions", args=[contract_id])
    agent_client.post(revisions_url, {"clause_ids": [str(clause.id)]}, format="json")

    status_url = reverse("contract-update-status", args=[contract_id])
    response = collaborator_client.patch(status_url, {"status": Contract.Status.AGREEMENT}, format="json")
    assert response.status_code == status.HTTP_200_OK
    contract.refresh_from_db()
    assert contract.status == Contract.Status.AGREEMENT


@pytest.mark.django_db
def test_non_owner_cannot_set_agreement(
    collaborator_client, member_client, clause_templates, contract_payload
):
    contract_id = collaborator_client.post(
        reverse("contract-list"), contract_payload, format="json"
    ).json()["id"]
    status_url = reverse("contract-update-status", args=[contract_id])
    response = member_client.patch(status_url, {"status": Contract.Status.AGREEMENT}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_contract_export_downloadable(
    collaborator_client, clause_templates, contract_payload
):
    contract_id = collaborator_client.post(
        reverse("contract-list"), contract_payload, format="json"
    ).json()["id"]
    contract = Contract.objects.get(id=contract_id)
    ContractFile.objects.create(
        contract=contract,
        pdf=ContentFile(b"PDF-DATA", name="contract.pdf"),
    )

    export_url = reverse("contract-export", args=[contract_id])
    response = collaborator_client.get(export_url)
    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content)
    assert content.startswith(b"PDF-DATA")
