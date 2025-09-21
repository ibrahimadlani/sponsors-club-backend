"""Integration tests covering the contracts workflow."""

from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

import pytest

from organisations.models import Collaborator
from users.models import User

from contracts.models import (
    ClauseTemplate,
    Contract,
    ContractClause,
    ContractFile,
    ContractRevision,
)


@pytest.fixture
def owner_client(owner_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(owner_user)
    return client


@pytest.fixture
def agent_client(agent_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(agent_user)
    return client


@pytest.fixture
def mandatory_clause_template():
    return ClauseTemplate.objects.create(
        category=ClauseTemplate.Category.LEGAL_OBLIGATIONS,
        title="Confidentialité",
        content="L'agent {{agent_name}} respecte la confidentialité.",
        placeholders=["agent_name"],
        is_mandatory=True,
        version=1,
    )


@pytest.fixture
def optional_clause_template():
    return ClauseTemplate.objects.create(
        category=ClauseTemplate.Category.FINANCIAL,
        title="Paiement",
        content="Paiement de {{amount}} euros.",
        placeholders=["amount"],
        is_mandatory=False,
        version=1,
    )


@pytest.fixture
def created_contract(
    owner_client,
    organisations_setup,
    agent_user,
    mandatory_clause_template,
):
    organisation = organisations_setup["organisation"]
    url = reverse("contract-list")
    payload = {
        "organisation_id": str(organisation.id),
        "agent_id": str(agent_user.agent_profile.id),
        "title": "Sponsoring 2025",
    }
    response = owner_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    contract_id = response.json()["id"]
    return Contract.objects.get(id=contract_id)


@pytest.mark.django_db
def test_create_contract_includes_mandatory_clauses(
    created_contract, mandatory_clause_template
):
    clauses = created_contract.clauses.all()
    assert clauses.count() == 1
    clause = clauses.first()
    assert clause.is_mandatory is True
    assert clause.template == mandatory_clause_template


@pytest.mark.django_db
def test_add_optional_clause_visible(
    owner_client,
    created_contract,
    optional_clause_template,
):
    url = reverse("contract-add-clause", args=[created_contract.id])
    response = owner_client.post(
        url, {"template_id": str(optional_clause_template.id)}, format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    clause = ContractClause.objects.get(id=payload["id"])
    assert clause.template == optional_clause_template
    assert clause.is_mandatory is False
    assert clause.is_modified is False

    detail_url = reverse("contract-detail", args=[created_contract.id])
    detail = owner_client.get(detail_url)
    assert detail.status_code == status.HTTP_200_OK
    clause_payload = detail.json()["clauses"]
    assert any(item["template_id"] == payload["template_id"] for item in clause_payload)


@pytest.mark.django_db
def test_add_clause_from_template_with_custom_content_marks_modified(
    owner_client,
    created_contract,
    optional_clause_template,
):
    url = reverse("contract-add-clause", args=[created_contract.id])
    response = owner_client.post(
        url,
        {
            "template_id": str(optional_clause_template.id),
            "content": "Paiement trimestriel.",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    clause = ContractClause.objects.get(id=response.json()["id"])
    assert clause.is_modified is True


@pytest.mark.django_db
def test_contract_creation_flow(owner_client, organisations_setup, agent_user, mandatory_clause_template):
    """End-to-end check that contract creation seeds metadata and mandatory clauses."""

    organisation = organisations_setup["organisation"]
    url = reverse("contract-list")
    payload = {
        "organisation_id": str(organisation.id),
        "agent_id": str(agent_user.agent_profile.id),
        "title": "Contrat Test",
    }

    response = owner_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    body = response.json()
    assert body["status"] == Contract.Status.DRAFT
    assert body["status_label"] == Contract.Status.DRAFT.label
    assert body["title"] == payload["title"]
    assert body["organisation"]["id"] == str(organisation.id)
    assert body["agent"]["id"] == str(agent_user.agent_profile.id)
    assert body["signed_file"] is None

    clauses = body["clauses"]
    assert len(clauses) == 1
    clause_payload = clauses[0]
    assert clause_payload["template_id"] == str(mandatory_clause_template.id)
    assert clause_payload["is_mandatory"] is True
    assert clause_payload["is_modified"] is False


@pytest.fixture
def alternative_clause_template():
    return ClauseTemplate.objects.create(
        category=ClauseTemplate.Category.LOGISTICS,
        title="Livraison",
        content="Livraison des équipements sous 30 jours.",
        placeholders=[],
        is_mandatory=False,
        version=1,
    )


@pytest.mark.django_db
def test_update_clause_can_apply_new_template(
    owner_client,
    created_contract,
    optional_clause_template,
    alternative_clause_template,
):
    add_url = reverse("contract-add-clause", args=[created_contract.id])
    response = owner_client.post(
        add_url, {"template_id": str(optional_clause_template.id)}, format="json"
    )
    clause_id = response.json()["id"]

    update_url = reverse("contract-update-clause", args=[created_contract.id, clause_id])
    patch = owner_client.patch(
        update_url,
        {"template_id": str(alternative_clause_template.id)},
        format="json",
    )
    assert patch.status_code == status.HTTP_200_OK
    clause = ContractClause.objects.get(id=clause_id)
    assert clause.template == alternative_clause_template
    assert clause.title == alternative_clause_template.title
    assert clause.content == alternative_clause_template.content
    assert clause.is_modified is False


@pytest.mark.django_db
def test_update_clause_with_template_and_custom_content_marks_modified(
    owner_client,
    created_contract,
    optional_clause_template,
    alternative_clause_template,
):
    add_url = reverse("contract-add-clause", args=[created_contract.id])
    response = owner_client.post(
        add_url, {"template_id": str(optional_clause_template.id)}, format="json"
    )
    clause_id = response.json()["id"]

    update_url = reverse("contract-update-clause", args=[created_contract.id, clause_id])
    patch = owner_client.patch(
        update_url,
        {
            "template_id": str(alternative_clause_template.id),
            "content": "Livraison sous 15 jours.",
        },
        format="json",
    )
    assert patch.status_code == status.HTTP_200_OK
    clause = ContractClause.objects.get(id=clause_id)
    assert clause.template == alternative_clause_template
    assert clause.is_modified is True


@pytest.mark.django_db
def test_list_clause_templates(owner_client, mandatory_clause_template, optional_clause_template):
    url = reverse("clause-template-list")
    response = owner_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    titles = {item["title"] for item in payload}
    assert {mandatory_clause_template.title, optional_clause_template.title} <= titles


@pytest.mark.django_db
def test_agent_can_view_clause_templates(agent_client, mandatory_clause_template):
    url = reverse("clause-template-list")
    response = agent_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    titles = [item["title"] for item in response.json()]
    assert mandatory_clause_template.title in titles


@pytest.mark.django_db
def test_agent_proposes_revision(
    agent_client,
    created_contract,
    optional_clause_template,
    owner_client,
):
    # Collaborator adds an optional clause which the agent proposes to modify
    owner_client.post(
        reverse("contract-add-clause", args=[created_contract.id]),
        {"template_id": str(optional_clause_template.id)},
        format="json",
    )
    clause = created_contract.clauses.filter(is_mandatory=False).first()

    revision_url = reverse("contract-create-revision", args=[created_contract.id])
    response = agent_client.post(
        revision_url,
        {"clause_ids": [str(clause.id)], "comment": "Proposition de mise à jour"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert ContractRevision.objects.filter(contract=created_contract).count() == 1


@pytest.mark.django_db
def test_agent_validation_flow(
    owner_client,
    agent_client,
    organisations_setup,
    agent_user,
    mandatory_clause_template,
):
    """Simulate an agent interacting with a freshly created contract."""

    organisation = organisations_setup["organisation"]
    create_url = reverse("contract-list")
    payload = {
        "organisation_id": str(organisation.id),
        "agent_id": str(agent_user.agent_profile.id),
        "title": "Validation Agent",
    }
    contract_resp = owner_client.post(create_url, payload, format="json")
    assert contract_resp.status_code == status.HTTP_201_CREATED
    contract_id = contract_resp.json()["id"]

    detail_url = reverse("contract-detail", args=[contract_id])
    detail_response = agent_client.get(detail_url)
    assert detail_response.status_code == status.HTTP_200_OK
    detail_payload = detail_response.json()
    assert detail_payload["id"] == contract_id
    assert detail_payload["status_label"] == Contract.Status.DRAFT.label
    assert detail_payload["signed_file"] is None

    revision_url = reverse("contract-create-revision", args=[contract_id])
    clause_id = detail_response.json()["clauses"][0]["id"]
    response = agent_client.post(
        revision_url,
        {
            "clause_ids": [clause_id],
            "comment": "Validation de la clause",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED

    status_url = reverse("contract-change-status", args=[contract_id])
    forbidden = agent_client.patch(
        status_url,
        {"status": Contract.Status.NEGOTIATION},
        format="json",
    )
    assert forbidden.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_owner_validates_contract_status(owner_client, created_contract):
    status_url = reverse("contract-change-status", args=[created_contract.id])

    response = owner_client.patch(
        status_url, {"status": Contract.Status.NEGOTIATION}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    created_contract.refresh_from_db()
    assert created_contract.status == Contract.Status.NEGOTIATION

    response = owner_client.patch(
        status_url, {"status": Contract.Status.AGREEMENT}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    created_contract.refresh_from_db()
    assert created_contract.status == Contract.Status.AGREEMENT


@pytest.mark.django_db
def test_non_owner_cannot_change_status(
    created_contract,
    organisations_setup,
    user_model,
):
    organisation = organisations_setup["organisation"]
    member = user_model.objects.create_user(
        email="member@test.com",
        password="pass1234",
        account_type=User.AccountType.COLLABORATOR,
    )
    Collaborator.objects.create(
        user=member,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Manager",
    )
    client = APIClient()
    client.force_authenticate(member)

    status_url = reverse("contract-change-status", args=[created_contract.id])
    response = client.patch(
        status_url, {"status": Contract.Status.NEGOTIATION}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_export_pdf_downloadable(owner_client, created_contract):
    ContractFile.objects.create(
        contract=created_contract,
        pdf=ContentFile(b"PDF", name="contrat.pdf"),
    )

    export_url = reverse("contract-export-pdf", args=[created_contract.id])
    response = owner_client.get(export_url)
    assert response.status_code == status.HTTP_200_OK
    disposition = response["Content-Disposition"]
    assert disposition.startswith("attachment; filename=\"")
    assert disposition.endswith(".pdf\"")

    detail_url = reverse("contract-detail", args=[created_contract.id])
    detail_payload = owner_client.get(detail_url).json()
    assert detail_payload["signed_file"]["filename"].endswith("contrat.pdf")


@pytest.mark.django_db
def test_contract_options_endpoint(owner_client, organisations_setup, agent_user):
    url = reverse("contract-options")
    response = owner_client.get(url)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    organisations = {item["id"] for item in payload["organisations"]}
    assert str(organisations_setup["organisation"].id) in organisations

    agent_ids = {item["id"] for item in payload["agents"]}
    assert str(agent_user.agent_profile.id) in agent_ids

    statuses = {item["value"] for item in payload["statuses"]}
    assert Contract.Status.DRAFT in statuses
    assert Contract.Status.AGREEMENT in statuses
