"""Tests for Phase 2 placeholder management functionality.

This module tests:
- Placeholder value updates
- Locked placeholder protection
- Template validation
- Automatic agreement revocation on placeholder changes
- Audit logging for placeholder updates
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from contracts.models import (
    ClauseTemplate,
    Contract,
    ContractAuditLog,
    ContractClause,
)

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an API client for making requests."""
    return APIClient()


@pytest.fixture
@pytest.mark.django_db
def clause_template_with_placeholders():
    """Create a clause template with placeholder definitions."""
    return ClauseTemplate.objects.create(
        title="Sponsorship Amount Template",
        category="financial",
        content="The sponsor shall pay {{currency}} {{amount}} per {{period}}.",
        is_mandatory=False,
        placeholders=[
            {"key": "currency", "label": "Currency", "default": "EUR"},
            {"key": "amount", "label": "Amount", "default": "10000"},
            {"key": "period", "label": "Period", "default": "month"},
        ],
    )


@pytest.fixture
def draft_contract_with_placeholder_clause(
    organisations_setup, agent_user, clause_template_with_placeholders
):
    """Create a draft contract with a clause containing placeholders."""
    collaborator = organisations_setup["collaborator"]

    contract = Contract.objects.create(
        organisation=organisations_setup["organisation"],
        agent=agent_user.agent_profile,
        initiated_by=collaborator,
        title="Sponsorship Contract with Placeholders",
        status=Contract.Status.DRAFT,
    )

    clause = ContractClause.objects.create(
        contract=contract,
        template=clause_template_with_placeholders,
        title=clause_template_with_placeholders.title,
        content=clause_template_with_placeholders.content,
        is_mandatory=False,
        placeholder_values={},
        locked_placeholders=[],
    )

    return {"contract": contract, "clause": clause}


@pytest.mark.django_db
class TestPlaceholderUpdates:
    """Test updating placeholder values in contract clauses."""

    def test_owner_can_update_placeholder_values(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Organisation owner can update placeholder values."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": "USD",
                    "amount": "15000",
                    "period": "year",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        clause.refresh_from_db()
        assert clause.placeholder_values["currency"] == "USD"
        assert clause.placeholder_values["amount"] == "15000"
        assert clause.placeholder_values["period"] == "year"

    def test_agent_can_update_placeholder_values(
        self, api_client, agent_user, draft_contract_with_placeholder_clause
    ):
        """Agent can update placeholder values during draft/negotiation."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=agent_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": "GBP",
                    "amount": "20000",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        clause.refresh_from_db()
        assert clause.placeholder_values["currency"] == "GBP"
        assert clause.placeholder_values["amount"] == "20000"

    def test_placeholder_values_merge_with_existing(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Updating placeholders merges with existing values."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Set initial values
        clause.placeholder_values = {"currency": "EUR", "amount": "10000"}
        clause.save()

        api_client.force_authenticate(user=owner_user)

        # Update only one placeholder
        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "period": "quarter",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        clause.refresh_from_db()
        assert clause.placeholder_values["currency"] == "EUR"
        assert clause.placeholder_values["amount"] == "10000"
        assert clause.placeholder_values["period"] == "quarter"

    def test_cannot_update_placeholder_after_agreement(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Cannot update placeholders after contract reaches agreement phase."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Move contract to agreement phase
        contract.status = Contract.Status.AGREEMENT
        contract.save()

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "amount": "99999",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestLockedPlaceholders:
    """Test locked placeholder protection."""

    def test_cannot_modify_locked_placeholder(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Locked placeholders cannot be modified."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Lock the currency placeholder
        clause.locked_placeholders = ["currency"]
        clause.placeholder_values = {"currency": "EUR"}
        clause.save()

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": "USD",  # Try to change locked value
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Errors are nested under placeholder_values field
        assert "placeholder_values" in response.data
        assert "currency" in response.data["placeholder_values"]
        assert "locked" in response.data["placeholder_values"]["currency"].lower()

    def test_can_modify_unlocked_placeholders_when_others_locked(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Can modify unlocked placeholders even when others are locked."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Lock only currency
        clause.locked_placeholders = ["currency"]
        clause.placeholder_values = {"currency": "EUR"}
        clause.save()

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "amount": "25000",  # Unlocked
                    "period": "month",  # Unlocked
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        clause.refresh_from_db()
        assert clause.placeholder_values["currency"] == "EUR"  # Unchanged
        assert clause.placeholder_values["amount"] == "25000"
        assert clause.placeholder_values["period"] == "month"

    def test_can_modify_placeholder_returns_true_for_unlocked(
        self, draft_contract_with_placeholder_clause
    ):
        """can_modify_placeholder returns True for unlocked placeholders."""
        clause = draft_contract_with_placeholder_clause["clause"]

        clause.locked_placeholders = ["currency"]
        clause.save()

        assert clause.can_modify_placeholder("amount") is True
        assert clause.can_modify_placeholder("period") is True

    def test_can_modify_placeholder_returns_false_for_locked(
        self, draft_contract_with_placeholder_clause
    ):
        """can_modify_placeholder returns False for locked placeholders."""
        clause = draft_contract_with_placeholder_clause["clause"]

        clause.locked_placeholders = ["currency", "amount"]
        clause.save()

        assert clause.can_modify_placeholder("currency") is False
        assert clause.can_modify_placeholder("amount") is False


@pytest.mark.django_db
class TestPlaceholderValidation:
    """Test placeholder validation against template."""

    def test_invalid_placeholder_key_rejected(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Placeholder keys not in template are rejected."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "invalid_key": "some value",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Errors are nested under placeholder_values field
        assert "placeholder_values" in response.data
        assert "invalid_key" in response.data["placeholder_values"]
        assert (
            "not found in clause template"
            in response.data["placeholder_values"]["invalid_key"]
        )

    def test_empty_placeholder_value_rejected(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Empty placeholder values are rejected."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "amount": "",  # Empty string
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Errors are nested under placeholder_values field
        assert "placeholder_values" in response.data
        assert "amount" in response.data["placeholder_values"]
        assert (
            "cannot have an empty value"
            in response.data["placeholder_values"]["amount"]
        )

    def test_null_placeholder_value_rejected(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Null placeholder values are rejected."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": None,
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPlaceholderRendering:
    """Test clause content rendering with placeholders."""

    def test_render_content_replaces_placeholders(
        self, draft_contract_with_placeholder_clause
    ):
        """render_content replaces placeholders with their values."""
        clause = draft_contract_with_placeholder_clause["clause"]

        clause.placeholder_values = {
            "currency": "USD",
            "amount": "50000",
            "period": "year",
        }
        clause.save()

        rendered = clause.render_content()

        assert "USD" in rendered
        assert "50000" in rendered
        assert "year" in rendered
        assert "{{currency}}" not in rendered
        assert "{{amount}}" not in rendered
        assert "{{period}}" not in rendered

    def test_render_content_with_partial_values(
        self, draft_contract_with_placeholder_clause
    ):
        """render_content leaves unreplaced placeholders as-is."""
        clause = draft_contract_with_placeholder_clause["clause"]

        clause.placeholder_values = {
            "currency": "EUR",
        }
        clause.save()

        rendered = clause.render_content()

        assert "EUR" in rendered
        assert "{{amount}}" in rendered  # Still present
        assert "{{period}}" in rendered  # Still present


@pytest.mark.django_db
class TestPlaceholderAgreementRevocation:
    """Test automatic agreement revocation when placeholders change."""

    def test_placeholder_update_revokes_owner_agreement(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Updating placeholders revokes owner agreement."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Record owner agreement
        contract.record_agreement(owner=True, agent=False)
        assert contract.owner_agreed_at is not None

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "amount": "30000",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        contract.refresh_from_db()
        assert contract.owner_agreed_at is None

    def test_placeholder_update_revokes_agent_agreement(
        self, api_client, owner_user, agent_user, draft_contract_with_placeholder_clause
    ):
        """Updating placeholders revokes agent agreement."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Record agent agreement
        contract.record_agreement(owner=False, agent=True)
        assert contract.agent_agreed_at is not None

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": "CHF",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        contract.refresh_from_db()
        assert contract.agent_agreed_at is None

    def test_placeholder_update_revokes_both_agreements(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Updating placeholders revokes both agreements."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        # Both parties agreed
        contract.record_agreement(owner=True, agent=True)
        assert contract.owner_agreed_at is not None
        assert contract.agent_agreed_at is not None

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "period": "quarter",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        contract.refresh_from_db()
        assert contract.owner_agreed_at is None
        assert contract.agent_agreed_at is None


@pytest.mark.django_db
class TestPlaceholderAuditLogging:
    """Test audit logging for placeholder updates."""

    def test_placeholder_update_creates_audit_log(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Placeholder updates create audit log entries."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        clause.placeholder_values = {"currency": "EUR"}
        clause.save()

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "currency": "USD",
                    "amount": "10000",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        # Check audit log was created
        audit_log = ContractAuditLog.objects.filter(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_MODIFIED,
        ).latest("timestamp")

        assert audit_log.actor == owner_user
        assert audit_log.action_details["field_changed"] == "placeholder_values"
        assert audit_log.action_details["old_values"]["currency"] == "EUR"
        assert audit_log.action_details["new_values"]["currency"] == "USD"
        assert audit_log.action_details["new_values"]["amount"] == "10000"

    def test_placeholder_audit_log_includes_clause_info(
        self, api_client, owner_user, draft_contract_with_placeholder_clause
    ):
        """Audit log includes clause identification details."""
        contract = draft_contract_with_placeholder_clause["contract"]
        clause = draft_contract_with_placeholder_clause["clause"]

        api_client.force_authenticate(user=owner_user)

        response = api_client.patch(
            f"/api/contracts/{contract.id}/clauses/{clause.id}/placeholders/",
            {
                "placeholder_values": {
                    "period": "semester",
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        audit_log = ContractAuditLog.objects.filter(
            contract=contract,
            action=ContractAuditLog.Action.CLAUSE_MODIFIED,
        ).latest("timestamp")

        assert str(clause.id) == audit_log.action_details["clause_id"]
        assert clause.title == audit_log.action_details["clause_title"]
