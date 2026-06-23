"""Tests for Phase 2 representation mandate functionality.

Tests cover the unified athletes.RepresentationMandate model, which is the
single source of truth for both entourage permission graphs and legal signing
proof (proof_document + verified fields).
"""

import pytest
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import RepresentationMandate
from contracts.models import Contract
from payments.models import PlatformFee

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_mandate_document():
    return SimpleUploadedFile(
        "mandate.pdf",
        b"PDF content here",
        content_type="application/pdf",
    )


@pytest.fixture
@pytest.mark.django_db
def athlete(agent_user):
    """Create an athlete managed by the agent_user."""
    from athletes.models import Athlete, Sport

    sport, _ = Sport.objects.get_or_create(name="Football", defaults={"emoji": "⚽"})
    return Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="John Doe",
        birth_date=date(1995, 1, 1),
        nationality="FRA",
    )


@pytest.fixture
@pytest.mark.django_db
def agent_mandate(agent_user, athlete, sample_mandate_document):
    """Valid LICENSED_AGENT mandate with proof document and staff verification."""
    return RepresentationMandate.objects.create(
        representative=agent_user.representative_profile,
        athlete=athlete,
        role=RepresentationMandate.Role.LICENSED_AGENT,
        proof_document=sample_mandate_document,
        verified=True,
        valid_from=date.today() - timedelta(days=30),
        valid_until=date.today() + timedelta(days=365),
        can_sign_legally=True,
    )


# ---------------------------------------------------------------------------
# Model creation tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMandateModel:
    """Test RepresentationMandate model field enrichment."""

    def test_create_licensed_agent_mandate_with_proof(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Can create a LICENSED_AGENT mandate with proof document."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
            can_sign_legally=True,
        )

        assert mandate.representative == agent_user.representative_profile
        assert mandate.athlete == athlete
        assert mandate.role == RepresentationMandate.Role.LICENSED_AGENT
        assert mandate.proof_document
        assert mandate.verified is False

    def test_create_parent_guardian_mandate_without_proof(self, agent_user, athlete):
        """Non-agent roles don't require a proof document."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.PARENT_GUARDIAN,
            verified=False,
        )

        assert mandate.role == RepresentationMandate.Role.PARENT_GUARDIAN
        assert not mandate.proof_document
        assert mandate.verified is False

    def test_mandate_string_representation(self, agent_mandate):
        """Mandate has a readable string representation."""
        str_repr = str(agent_mandate)
        assert agent_mandate.athlete.full_name in str_repr

    def test_new_proof_fields_default_to_null(self, agent_user, athlete):
        """Newly created mandates have null proof fields by default."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.COACH,
        )
        assert mandate.proof_document.name in (None, "")
        assert mandate.verified is False
        assert mandate.verified_by is None
        assert mandate.verified_at is None
        assert mandate.valid_from is None
        assert mandate.valid_until is None


# ---------------------------------------------------------------------------
# is_valid() tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMandateValidity:
    """Test the unified is_valid() logic."""

    def test_verified_agent_mandate_within_dates_is_valid(self, agent_mandate):
        """Verified LICENSED_AGENT mandate within validity period is valid."""
        assert agent_mandate.is_valid() is True

    def test_unverified_agent_mandate_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """LICENSED_AGENT mandate without verification is not valid."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
            can_sign_legally=True,
        )
        assert mandate.is_valid() is False

    def test_agent_mandate_without_proof_document_is_invalid(self, agent_user, athlete):
        """LICENSED_AGENT mandate without proof_document is not valid."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            verified=True,
            valid_from=date.today(),
            can_sign_legally=True,
        )
        assert mandate.is_valid() is False

    def test_inactive_mandate_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Inactive mandate is not valid regardless of other fields."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today(),
            is_active=False,
        )
        assert mandate.is_valid() is False

    def test_mandate_before_valid_from_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate is invalid before its valid_from date."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today() + timedelta(days=10),
            can_sign_legally=True,
        )
        assert mandate.is_valid() is False

    def test_expired_mandate_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate past its valid_until date is invalid."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=365),
            valid_until=date.today() - timedelta(days=1),
            can_sign_legally=True,
        )
        assert mandate.is_valid() is False

    def test_mandate_without_end_date_is_valid_indefinitely(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate without valid_until is valid indefinitely."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today(),
            can_sign_legally=True,
        )
        assert mandate.is_valid() is True

    def test_is_valid_accepts_custom_check_date(
        self, agent_user, athlete, sample_mandate_document
    ):
        """is_valid() evaluates against a caller-supplied date."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=30),
            can_sign_legally=True,
        )

        assert mandate.is_valid(check_date=date.today()) is True
        assert mandate.is_valid(check_date=date.today() + timedelta(days=60)) is False

    def test_parent_guardian_valid_without_proof(self, agent_user, athlete):
        """PARENT_GUARDIAN mandate is valid without proof document when active."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.PARENT_GUARDIAN,
            verified=False,
        )
        assert mandate.is_valid() is True


# ---------------------------------------------------------------------------
# Mandate verification workflow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMandateVerification:
    """Test the staff verification workflow."""

    def test_staff_can_verify_mandate(
        self, agent_user, athlete, sample_mandate_document, owner_user
    ):
        """Staff can mark a mandate as verified."""
        mandate = RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
            can_sign_legally=True,
        )

        from django.utils import timezone as tz

        owner_user.is_staff = True
        owner_user.save()

        mandate.verified = True
        mandate.verified_by = owner_user
        mandate.verified_at = tz.now()
        mandate.save()

        assert mandate.verified is True
        assert mandate.verified_by == owner_user
        assert mandate.verified_at is not None
        assert mandate.is_valid() is True


# ---------------------------------------------------------------------------
# Signing gate: agent mandate check via athletes.RepresentationMandate
# ---------------------------------------------------------------------------


def _paid_fee(contract):
    """Create a PAID PlatformFee so the 402 paywall is cleared."""
    return PlatformFee.objects.create(
        contract=contract,
        fee_type=PlatformFee.FeeType.MATERIAL_FIXED_FEE,
        amount_due="49.00",
        status=PlatformFee.Status.PAID,
    )


@pytest.mark.django_db
class TestSignatureWithMandateValidation:
    """init_signing enforces a valid LICENSED_AGENT mandate for the agent."""

    def test_cannot_initiate_signing_without_agent_mandate(
        self, api_client, owner_user, agent_user, organisations_setup
    ):
        """Returns 400 when the agent has no valid mandate in athletes model."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract without Agent Mandate",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mandate" in response.data["detail"].lower()
        assert "missing_mandates" in response.data
        assert len(response.data["missing_mandates"]) > 0

    def test_can_initiate_signing_with_valid_agent_mandate(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        agent_mandate,
    ):
        """Returns 201 when the agent holds a valid LICENSED_AGENT mandate."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Valid Agent Mandate",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-456"},
            format="json",
        )

        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_200_OK]
        assert response.data["envelope_id"] == "test-envelope-456"

    def test_expired_mandate_prevents_signing(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        sample_mandate_document,
    ):
        """Expired agent mandate is rejected by the signing gate."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Expired Mandate",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)
        RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=365),
            valid_until=date.today() - timedelta(days=1),
            can_sign_legally=True,
        )

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-789"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mandate" in response.data["detail"].lower()

    def test_unverified_mandate_prevents_signing(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        sample_mandate_document,
    ):
        """Unverified agent mandate is rejected by the signing gate."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Unverified Mandate",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)
        RepresentationMandate.objects.create(
            representative=agent_user.representative_profile,
            athlete=athlete,
            role=RepresentationMandate.Role.LICENSED_AGENT,
            proof_document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
            can_sign_legally=True,
        )

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-999"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mandate" in response.data["detail"].lower()

    def test_organisation_side_requires_no_separate_mandate_document(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        agent_mandate,
    ):
        """Signing succeeds without a separate collaborator mandate document.

        The OWNER role on Collaborator is sufficient to represent the org.
        """
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract - no collab doc needed",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-collab"},
            format="json",
        )

        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_200_OK]


# ---------------------------------------------------------------------------
# Missing mandate detail response
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMandateMissingDetails:
    """Missing mandate response lists which parties are blocking signing."""

    def test_missing_mandates_includes_agent_details(
        self, api_client, owner_user, agent_user, athlete, organisations_setup
    ):
        """Response includes the agent party when their mandate is absent."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract for Missing Mandate Details",
            status=Contract.Status.SIGNING,
        )
        _paid_fee(contract)

        api_client.force_authenticate(user=owner_user)
        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-111"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        missing = response.data["missing_mandates"]
        assert isinstance(missing, list)
        assert any(m["party"] == "agent" for m in missing)
