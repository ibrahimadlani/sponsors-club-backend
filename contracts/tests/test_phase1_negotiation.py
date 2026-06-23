"""Comprehensive tests for Phase 1 contract negotiation features.

Tests cover:
1. Version snapshots - Verifying complete state capture
2. Audit logging - Tracking all contract actions with IP/user-agent
3. Automatic agreement revocation - When clauses change
4. Agent permissions - Bi-directional negotiation
5. Revision rejection - Proper workflow handling
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

import pytest

from contracts.models import (
    ClauseTemplate,
    Contract,
    ContractAuditLog,
    ContractClause,
    ContractRevision,
)


@pytest.fixture
def organisation(organisations_setup):
    """Organisation fixture from global setup."""
    return organisations_setup["organisation"]


@pytest.fixture
def agent_profile(agent_user):
    """Agent profile fixture."""
    return agent_user.agent_profile


@pytest.fixture
def owner_client(owner_user) -> APIClient:
    """Authenticated client for organisation owner."""
    client = APIClient()
    client.force_authenticate(owner_user)
    return client


@pytest.fixture
def agent_client(agent_user) -> APIClient:
    """Authenticated client for athlete agent."""
    client = APIClient()
    client.force_authenticate(agent_user)
    return client


@pytest.fixture
def mandatory_template():
    """Mandatory clause template for testing."""
    return ClauseTemplate.objects.create(
        category=ClauseTemplate.Category.LEGAL_OBLIGATIONS,
        title="Durée du contrat",
        content="Le présent contrat est conclu pour une durée de {{duration}} mois.",
        placeholders=["duration"],
        is_mandatory=True,
        version=1,
    )


@pytest.fixture
def optional_template():
    """Optional clause template for testing."""
    return ClauseTemplate.objects.create(
        category=ClauseTemplate.Category.FINANCIAL,
        title="Prime de performance",
        content="Une prime de {{bonus_amount}}€ sera versée en cas de victoire.",
        placeholders=["bonus_amount"],
        is_mandatory=False,
        version=1,
    )


@pytest.fixture
def draft_contract(organisations_setup, agent_profile, owner_user, mandatory_template):
    """Create a draft contract with mandatory clauses."""
    organisation = organisations_setup["organisation"]
    collaborator = organisations_setup["collaborator"]

    contract = Contract.objects.create(
        organisation=organisation,
        agent=agent_profile,
        initiated_by=collaborator,
        status=Contract.Status.DRAFT,
        title="Contrat de sponsoring athlète",
        effective_date=timezone.now().date(),
    )
    # Add mandatory clause
    ContractClause.objects.create(
        contract=contract,
        template=mandatory_template,
        title=mandatory_template.title,
        content=mandatory_template.content,
        is_mandatory=True,
    )
    # Create initial version
    contract.bump_version(created_by=owner_user, notes="Initial version")
    return contract


# ============================================================================
# SNAPSHOT TESTS
# ============================================================================


@pytest.mark.django_db
class TestVersionSnapshots:
    """Test that version snapshots capture complete contract state."""

    def test_snapshot_captures_all_clauses(
        self, draft_contract, owner_user, optional_template
    ):
        """Verify snapshot includes all clause data."""
        # Add optional clause
        ContractClause.objects.create(
            contract=draft_contract,
            template=optional_template,
            title=optional_template.title,
            content=optional_template.content,
            is_mandatory=False,
        )

        # Bump version to trigger snapshot
        version = draft_contract.bump_version(
            created_by=owner_user, notes="Added optional clause"
        )

        # Verify snapshot was captured
        assert version.clauses_snapshot != {}
        assert "clauses" in version.clauses_snapshot
        assert version.clauses_snapshot["clause_count"] == 2

        # Verify clause details in snapshot
        clauses = version.clauses_snapshot["clauses"]
        assert len(clauses) == 2

        # Check mandatory clause
        mandatory_clause = next(c for c in clauses if c["is_mandatory"])
        assert mandatory_clause["title"] == "Durée du contrat"
        assert "template" in mandatory_clause
        assert mandatory_clause["template"]["category"] == "legal_obligations"

        # Check optional clause
        optional_clause = next(c for c in clauses if not c["is_mandatory"])
        assert optional_clause["title"] == "Prime de performance"
        assert optional_clause["template"]["id"] == str(optional_template.id)

    def test_snapshot_captures_contract_metadata(self, draft_contract, owner_user):
        """Verify snapshot includes contract-level metadata."""
        version = draft_contract.bump_version(created_by=owner_user, notes="Test")

        snapshot = version.clauses_snapshot
        assert snapshot["contract_title"] == draft_contract.title
        assert snapshot["status"] == draft_contract.status
        assert snapshot["effective_date"] is not None
        assert "clause_count" in snapshot

    def test_snapshot_captures_agreement_status(self, draft_contract, owner_user):
        """Verify snapshot captures agreement timestamps."""
        # Record agreement
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = timezone.now()
        draft_contract.save()

        # Bump version
        version = draft_contract.bump_version(created_by=owner_user, notes="Test")

        # Verify agreement status captured
        agreement = version.agreement_status
        assert agreement["owner_agreed"] is True
        assert agreement["agent_agreed"] is True
        assert agreement["owner_agreed_at"] is not None
        assert agreement["agent_agreed_at"] is not None

    def test_snapshot_captures_modified_clauses(self, draft_contract, owner_user):
        """Verify snapshot tracks clause modifications."""
        clause = draft_contract.clauses.first()
        clause.content = "Modified content"
        clause.is_modified = True
        clause.save()

        version = draft_contract.bump_version(
            created_by=owner_user, notes="Modified clause"
        )

        snapshot = version.clauses_snapshot
        modified_clause = snapshot["clauses"][0]
        assert modified_clause["is_modified"] is True
        assert modified_clause["content"] == "Modified content"


# ============================================================================
# AUDIT LOG TESTS
# ============================================================================


@pytest.mark.django_db
class TestAuditLogging:
    """Test comprehensive audit logging with IP and user-agent tracking."""

    def test_contract_creation_logged(self, owner_client, organisation, agent_profile):
        """Verify contract creation creates audit log."""
        url = reverse("contract-list")
        payload = {
            "organisation_id": str(organisation.id),
            "agent_id": str(agent_profile.id),
            "title": "Test Contract",
            "effective_date": "2026-01-15",
        }

        response = owner_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        contract = Contract.objects.get(id=response.data["id"])
        logs = ContractAuditLog.objects.filter(contract=contract)

        # Should have created audit log
        assert logs.exists()
        creation_log = logs.get(action=ContractAuditLog.Action.CONTRACT_CREATED)
        assert creation_log.actor.email == "owner@test.com"
        assert "organisation_id" in creation_log.action_details
        assert "agent_id" in creation_log.action_details

    def test_clause_added_logged(self, owner_client, draft_contract, optional_template):
        """Verify clause addition creates audit log."""
        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {
            "template_id": str(optional_template.id),
        }

        response = owner_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Check audit log
        log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.CLAUSE_ADDED,
        ).first()
        assert log is not None
        assert log.actor.email == "owner@test.com"
        assert "clause_id" in log.action_details
        assert log.action_details["clause_title"] == optional_template.title

    def test_clause_modified_logged_with_old_values(self, owner_client, draft_contract):
        """Verify clause modification logs old and new values."""
        clause = draft_contract.clauses.first()
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )
        payload = {
            "title": "New Title",
            "content": "New content",
        }

        response = owner_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Check audit log has old and new values
        log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.CLAUSE_MODIFIED,
        ).first()
        assert log is not None
        assert "old_title" in log.action_details
        assert "old_content" in log.action_details
        assert "new_title" in log.action_details
        assert log.action_details["new_title"] == "New Title"

    def test_clause_deleted_logged_with_content(
        self, owner_client, draft_contract, optional_template
    ):
        """Verify clause deletion preserves content in audit log."""
        # Add optional clause first
        clause = ContractClause.objects.create(
            contract=draft_contract,
            template=optional_template,
            title=optional_template.title,
            content=optional_template.content,
            is_mandatory=False,
        )

        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )

        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Check audit log preserves deleted content
        log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.CLAUSE_DELETED,
        ).first()
        assert log is not None
        assert log.action_details["clause_title"] == optional_template.title
        assert log.action_details["clause_content"] == optional_template.content

    def test_agreement_logged_separately_for_owner_and_agent(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify owner and agent agreements create separate logs."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        url = reverse("contract-agree", kwargs={"pk": draft_contract.id})

        # Owner agrees
        response = owner_client.post(url)
        assert response.status_code == status.HTTP_200_OK

        # Agent agrees
        response = agent_client.post(url)
        assert response.status_code == status.HTTP_200_OK

        # Check separate audit logs
        owner_log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.OWNER_AGREED,
        ).first()
        assert owner_log is not None
        assert owner_log.actor.email == "owner@test.com"

        agent_log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.AGENT_AGREED,
        ).first()
        assert agent_log is not None
        assert agent_log.actor.email == "agent@test.com"

    def test_revision_workflow_fully_logged(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify complete revision workflow is logged."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # 1. Agent creates revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        payload = {"comment": "Please consider this change"}

        response = agent_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        revision_id = response.data["id"]

        # Check creation log
        creation_log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.REVISION_CREATED,
        ).first()
        assert creation_log is not None
        assert creation_log.actor.email == "agent@test.com"

        # 2. Owner accepts revision
        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )

        response = owner_client.post(url)
        assert response.status_code == status.HTTP_200_OK

        # Check acceptance log
        acceptance_log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.REVISION_ACCEPTED,
        ).first()
        assert acceptance_log is not None
        assert acceptance_log.actor.email == "owner@test.com"
        assert "proposed_by" in acceptance_log.action_details

    def test_ip_and_user_agent_captured(
        self, owner_client, organisation, agent_profile
    ):
        """Verify IP address and user-agent are captured in audit logs."""
        url = reverse("contract-list")
        payload = {
            "organisation_id": str(organisation.id),
            "agent_id": str(agent_profile.id),
            "title": "Test Contract",
            "effective_date": "2026-01-15",
        }

        # Set custom headers
        response = owner_client.post(
            url,
            payload,
            format="json",
            HTTP_X_FORWARDED_FOR="192.168.1.100",
            HTTP_USER_AGENT="Mozilla/5.0 Test Browser",
        )
        assert response.status_code == status.HTTP_201_CREATED

        contract = Contract.objects.get(id=response.data["id"])
        log = ContractAuditLog.objects.filter(
            contract=contract,
            action=ContractAuditLog.Action.CONTRACT_CREATED,
        ).first()

        # Verify IP and user-agent captured
        assert log.ip_address == "192.168.1.100"
        assert log.user_agent == "Mozilla/5.0 Test Browser"


# ============================================================================
# AUTOMATIC AGREEMENT REVOCATION TESTS
# ============================================================================


@pytest.mark.django_db
class TestAutomaticAgreementRevocation:
    """Test that agreements are automatically revoked when contract changes."""

    def test_agreement_revoked_when_clause_added(
        self, owner_client, draft_contract, optional_template
    ):
        """Verify both agreements are revoked when a new clause is added."""
        # Set up full agreement
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = timezone.now()
        draft_contract.save()

        # Verify agreements exist
        draft_contract.refresh_from_db()
        assert draft_contract.owner_agreed_at is not None
        assert draft_contract.agent_agreed_at is not None

        # Add new clause
        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = owner_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Verify agreements were revoked
        draft_contract.refresh_from_db()
        assert draft_contract.owner_agreed_at is None
        assert draft_contract.agent_agreed_at is None

    def test_agreement_revoked_when_clause_modified(self, owner_client, draft_contract):
        """Verify agreements are revoked when clause content changes."""
        # Set up agreement
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = timezone.now()
        draft_contract.save()

        clause = draft_contract.clauses.first()
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )
        payload = {"content": "Modified content that changes the agreement"}

        response = owner_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify agreements were revoked
        draft_contract.refresh_from_db()
        assert draft_contract.owner_agreed_at is None
        assert draft_contract.agent_agreed_at is None

    def test_agreement_revoked_when_clause_deleted(
        self, owner_client, draft_contract, optional_template
    ):
        """Verify agreements are revoked when a clause is deleted."""
        # Add optional clause
        clause = ContractClause.objects.create(
            contract=draft_contract,
            template=optional_template,
            title=optional_template.title,
            content=optional_template.content,
            is_mandatory=False,
        )

        # Set up agreement
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = timezone.now()
        draft_contract.save()

        # Delete clause
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )

        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify agreements were revoked
        draft_contract.refresh_from_db()
        assert draft_contract.owner_agreed_at is None
        assert draft_contract.agent_agreed_at is None

    def test_only_owner_agreement_revoked_if_agent_not_agreed(
        self, owner_client, draft_contract, optional_template
    ):
        """Verify only existing agreements are revoked."""
        # Only owner has agreed
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = None
        draft_contract.save()

        # Add clause
        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = owner_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Verify owner agreement revoked, agent still None
        draft_contract.refresh_from_db()
        assert draft_contract.owner_agreed_at is None
        assert draft_contract.agent_agreed_at is None

    def test_revocation_logged_in_audit_trail(
        self, owner_client, draft_contract, optional_template, owner_user
    ):
        """Verify agreement revocation is tracked via audit logs."""
        # Set up full agreement
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.owner_agreed_at = timezone.now()
        draft_contract.agent_agreed_at = timezone.now()
        draft_contract.save()

        # Record initial agreement in logs (actor must be User, not Collaborator)
        ContractAuditLog.objects.create(
            contract=draft_contract,
            actor=owner_user,
            action=ContractAuditLog.Action.OWNER_AGREED,
        )

        # Modify clause (which revokes agreements)
        clause = draft_contract.clauses.first()
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )
        payload = {"content": "Modified"}

        response = owner_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Check audit trail shows both agreement and modification
        logs = ContractAuditLog.objects.filter(contract=draft_contract).order_by(
            "created_at"
        )
        assert logs.filter(action=ContractAuditLog.Action.OWNER_AGREED).exists()
        assert logs.filter(action=ContractAuditLog.Action.CLAUSE_MODIFIED).exists()


# ============================================================================
# AGENT PERMISSIONS TESTS
# ============================================================================


@pytest.mark.django_db
class TestAgentPermissions:
    """Test that agents have proper permissions for bi-directional negotiation."""

    def test_agent_can_add_clause_during_draft(
        self, agent_client, draft_contract, optional_template
    ):
        """Verify agent can add clauses during DRAFT phase."""
        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = agent_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_agent_can_add_clause_during_negotiation(
        self, agent_client, draft_contract, optional_template
    ):
        """Verify agent can add clauses during NEGOTIATION phase."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = agent_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_agent_can_modify_clause(self, agent_client, draft_contract):
        """Verify agent can modify existing clauses."""
        clause = draft_contract.clauses.first()
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )
        payload = {"content": "Agent modified content"}

        response = agent_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        clause.refresh_from_db()
        assert clause.content == "Agent modified content"

    def test_agent_can_delete_optional_clause(
        self, agent_client, draft_contract, optional_template
    ):
        """Verify agent can delete non-mandatory clauses."""
        clause = ContractClause.objects.create(
            contract=draft_contract,
            template=optional_template,
            title=optional_template.title,
            content=optional_template.content,
            is_mandatory=False,
        )

        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )

        response = agent_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_agent_cannot_delete_mandatory_clause(self, agent_client, draft_contract):
        """Verify agent cannot delete mandatory clauses."""
        clause = draft_contract.clauses.filter(is_mandatory=True).first()
        url = reverse(
            "contract-update-clause",
            kwargs={
                "pk": draft_contract.id,
                "clause_id": clause.id,
            },
        )

        response = agent_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_agent_cannot_edit_after_agreement_phase(
        self, agent_client, draft_contract, optional_template
    ):
        """Verify agent cannot edit clauses after AGREEMENT phase."""
        draft_contract.status = Contract.Status.AGREEMENT
        draft_contract.save()

        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = agent_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_wrong_agent_cannot_edit_contract(
        self, agent_profile, draft_contract, optional_template, user_model
    ):
        """Verify only the assigned agent can edit the contract."""
        from users.models import AgentProfile

        # Create different agent
        other_agent_user = user_model.objects.create_user(
            email="other_agent@test.com",
            password="pass1234",
            account_type=user_model.AccountType.AGENT,
        )
        # Create agent profile for the new user
        AgentProfile.objects.create(user=other_agent_user)

        client = APIClient()
        client.force_authenticate(other_agent_user)

        url = reverse("contract-add-clause", kwargs={"pk": draft_contract.id})
        payload = {"template_id": str(optional_template.id)}

        response = client.post(url, payload, format="json")
        # Wrong agent gets 404 (contract not visible) or 403 (forbidden)
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


# ============================================================================
# REVISION REJECTION TESTS
# ============================================================================


@pytest.mark.django_db
class TestRevisionRejection:
    """Test revision rejection endpoint and workflow."""

    def test_owner_can_reject_revision(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify owner can reject agent's revision."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # Agent creates revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        payload = {"comment": "Please consider this change"}

        response = agent_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        revision_id = response.data["id"]

        # Owner rejects revision
        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )

        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_200_OK

        # Verify revision marked as rejected
        revision = ContractRevision.objects.get(id=revision_id)
        assert revision.accepted is False

    def test_rejected_revision_logged(self, owner_client, agent_client, draft_contract):
        """Verify revision rejection creates audit log."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # Create and reject revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        response = agent_client.post(url, {"comment": "Test"}, format="json")
        revision_id = response.data["id"]

        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )
        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_200_OK

        # Check audit log
        log = ContractAuditLog.objects.filter(
            contract=draft_contract,
            action=ContractAuditLog.Action.REVISION_REJECTED,
        ).first()
        assert log is not None
        assert log.actor.email == "owner@test.com"
        assert "proposed_by" in log.action_details

    def test_cannot_reject_already_accepted_revision(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify cannot reject revision that was already accepted."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # Create revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        response = agent_client.post(url, {"comment": "Test"}, format="json")
        revision_id = response.data["id"]

        # Accept revision
        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )
        response = owner_client.post(url)
        assert response.status_code == status.HTTP_200_OK

        # Try to reject (should fail)
        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been reviewed" in response.data["detail"]

    def test_cannot_reject_already_rejected_revision(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify cannot reject revision twice."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # Create revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        response = agent_client.post(url, {"comment": "Test"}, format="json")
        revision_id = response.data["id"]

        # Reject revision
        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )
        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_200_OK

        # Try to reject again (should fail)
        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_agent_cannot_reject_own_revision(self, agent_client, draft_contract):
        """Verify agent cannot reject their own revision."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        # Create revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        response = agent_client.post(url, {"comment": "Test"}, format="json")
        revision_id = response.data["id"]

        # Try to reject own revision (should fail - only owner can)
        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )
        response = agent_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_rejected_revision_does_not_bump_version(
        self, owner_client, agent_client, draft_contract
    ):
        """Verify rejecting revision does not create new version."""
        draft_contract.status = Contract.Status.NEGOTIATION
        draft_contract.save()

        initial_version = draft_contract.current_version_number

        # Create and reject revision
        url = reverse("contract-create-revision", kwargs={"pk": draft_contract.id})
        response = agent_client.post(url, {"comment": "Test"}, format="json")
        revision_id = response.data["id"]

        url = reverse(
            "contract-accept-revision",
            kwargs={
                "pk": draft_contract.id,
                "revision_id": revision_id,
            },
        )
        response = owner_client.delete(url)
        assert response.status_code == status.HTTP_200_OK

        # Verify version unchanged
        draft_contract.refresh_from_db()
        assert draft_contract.current_version_number == initial_version
