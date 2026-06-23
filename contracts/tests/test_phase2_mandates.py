"""Tests for Phase 2 representation mandate functionality.

This module tests:
- Mandate model creation and validation
- XOR constraint (agent+athlete OR collaborator+organisation)
- Mandate verification workflow
- Mandate validity checks
- Signature authorization with mandate validation
"""

import pytest
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APIClient

from contracts.models import (
    Contract,
    RepresentationMandate,
)
from athletes.models import Athlete

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an API client for making requests."""
    return APIClient()


@pytest.fixture
def sample_mandate_document():
    """Create a sample PDF document for mandate upload."""
    return SimpleUploadedFile(
        "mandate.pdf",
        b"PDF content here",
        content_type="application/pdf",
    )


@pytest.fixture
@pytest.mark.django_db
def athlete(agent_user):
    """Create an athlete for mandate testing."""
    from athletes.models import Sport

    # Create a sport if needed
    sport, _ = Sport.objects.get_or_create(name="Football", defaults={"emoji": "⚽"})

    # Create athlete
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="John Doe",
        birth_date=date(1995, 1, 1),
        nationality="FRA",
    )
    return athlete


@pytest.fixture
@pytest.mark.django_db
def agent_mandate(agent_user, athlete, sample_mandate_document):
    """Create an agent representation mandate."""
    return RepresentationMandate.objects.create(
        agent=agent_user.agent_profile,
        athlete=athlete,
        document=sample_mandate_document,
        verified=True,
        valid_from=date.today() - timedelta(days=30),
        valid_until=date.today() + timedelta(days=365),
    )


@pytest.fixture
def collaborator_mandate(organisations_setup, sample_mandate_document):
    """Create a collaborator representation mandate."""
    collaborator = organisations_setup["collaborator"]
    organisation = organisations_setup["organisation"]

    return RepresentationMandate.objects.create(
        collaborator=collaborator,
        organisation=organisation,
        document=sample_mandate_document,
        verified=True,
        valid_from=date.today() - timedelta(days=30),
        valid_until=date.today() + timedelta(days=365),
    )


@pytest.mark.django_db
class TestMandateModel:
    """Test RepresentationMandate model behavior."""

    def test_create_agent_mandate(self, agent_user, athlete, sample_mandate_document):
        """Can create a mandate for an agent representing an athlete."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
        )

        assert mandate.agent == agent_user.agent_profile
        assert mandate.athlete == athlete
        assert mandate.collaborator is None
        assert mandate.organisation is None
        assert mandate.verified is False

    def test_create_collaborator_mandate(
        self, organisations_setup, sample_mandate_document
    ):
        """Can create a mandate for a collaborator representing an organisation."""
        collaborator = organisations_setup["collaborator"]
        organisation = organisations_setup["organisation"]

        mandate = RepresentationMandate.objects.create(
            collaborator=collaborator,
            organisation=organisation,
            document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
        )

        assert mandate.collaborator == collaborator
        assert mandate.organisation == organisation
        assert mandate.agent is None
        assert mandate.athlete is None
        assert mandate.verified is False

    def test_xor_constraint_prevents_both_types(
        self, agent_user, athlete, organisations_setup, sample_mandate_document
    ):
        """XOR constraint prevents setting both agent and collaborator."""
        from django.db import transaction

        # Use atomic block to handle the integrity error properly
        with transaction.atomic():
            with pytest.raises(IntegrityError):
                RepresentationMandate.objects.create(
                    agent=agent_user.agent_profile,
                    athlete=athlete,
                    collaborator=organisations_setup["collaborator"],
                    organisation=organisations_setup["organisation"],
                    document=sample_mandate_document,
                    verified=False,
                    valid_from=date.today(),
                )

    def test_mandate_string_representation(self, agent_mandate):
        """Mandate has a meaningful string representation."""
        str_repr = str(agent_mandate)
        assert "agent" in str_repr.lower() or agent_mandate.agent.name in str_repr


@pytest.mark.django_db
class TestMandateValidity:
    """Test mandate validity checking logic."""

    def test_verified_mandate_within_dates_is_valid(self, agent_mandate):
        """Verified mandate within validity period is valid."""
        assert agent_mandate.is_valid() is True

    def test_unverified_mandate_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Unverified mandate is not valid."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=False,  # Not verified
            valid_from=date.today(),
        )

        assert mandate.is_valid() is False

    def test_mandate_before_valid_from_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate before valid_from date is invalid."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() + timedelta(days=10),  # Future date
        )

        assert mandate.is_valid() is False

    def test_mandate_after_valid_until_is_invalid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate after valid_until date is invalid."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=365),
            valid_until=date.today() - timedelta(days=1),  # Expired
        )

        assert mandate.is_valid() is False

    def test_mandate_without_end_date_is_valid(
        self, agent_user, athlete, sample_mandate_document
    ):
        """Mandate without valid_until (indefinite) is valid if verified."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today(),
            valid_until=None,  # Indefinite
        )

        assert mandate.is_valid() is True

    def test_is_valid_accepts_custom_check_date(
        self, agent_user, athlete, sample_mandate_document
    ):
        """is_valid() can check validity for a specific date."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )

        # Valid today
        assert mandate.is_valid(check_date=date.today()) is True

        # Invalid 60 days from now
        future_date = date.today() + timedelta(days=60)
        assert mandate.is_valid(check_date=future_date) is False


@pytest.mark.django_db
class TestMandateVerification:
    """Test mandate verification workflow."""

    def test_staff_can_verify_mandate(
        self, agent_user, athlete, sample_mandate_document, owner_user
    ):
        """Staff users can verify mandates."""
        mandate = RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=False,
            valid_from=date.today(),
        )

        # Make owner_user staff
        owner_user.is_staff = True
        owner_user.save()

        # Verify the mandate
        from django.utils import timezone

        mandate.verified = True
        mandate.verified_by = owner_user
        mandate.verified_at = timezone.now()
        mandate.save()

        assert mandate.verified is True
        assert mandate.verified_by == owner_user
        assert mandate.verified_at is not None
        assert mandate.is_valid() is True


@pytest.mark.django_db
class TestSignatureWithMandateValidation:
    """Test signature authorization with mandate validation."""

    def test_cannot_initiate_signing_without_agent_mandate(
        self, api_client, owner_user, agent_user, athlete, organisations_setup
    ):
        """Cannot initiate signing if agent mandate is missing."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract without Agent Mandate",
            status=Contract.Status.SIGNING,
        )

        # Create only collaborator mandate (agent mandate missing)
        RepresentationMandate.objects.create(
            collaborator=collaborator,
            organisation=organisations_setup["organisation"],
            document=SimpleUploadedFile(
                "mandate.pdf", b"content", content_type="application/pdf"
            ),
            verified=True,
            valid_from=date.today() - timedelta(days=30),
        )

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

    def test_cannot_initiate_signing_without_collaborator_mandate(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        sample_mandate_document,
    ):
        """Cannot initiate signing if collaborator mandate is missing."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract without Collaborator Mandate",
            status=Contract.Status.SIGNING,
        )

        # Create only agent mandate (collaborator mandate missing)
        RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=30),
        )

        api_client.force_authenticate(user=owner_user)

        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mandate" in response.data["detail"].lower()
        assert "missing_mandates" in response.data

    def test_can_initiate_signing_with_valid_mandates(
        self,
        api_client,
        owner_user,
        agent_user,
        athlete,
        organisations_setup,
        agent_mandate,
        collaborator_mandate,
    ):
        """Can initiate signing when both mandates are valid."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Valid Mandates",
            status=Contract.Status.SIGNING,
        )

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
        """Expired mandate prevents signature initiation."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Expired Mandate",
            status=Contract.Status.SIGNING,
        )

        # Create expired agent mandate
        RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=365),
            valid_until=date.today() - timedelta(days=1),  # Expired yesterday
        )

        # Create valid collaborator mandate
        RepresentationMandate.objects.create(
            collaborator=collaborator,
            organisation=organisations_setup["organisation"],
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=30),
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
        """Unverified mandate prevents signature initiation."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract with Unverified Mandate",
            status=Contract.Status.SIGNING,
        )

        # Create unverified agent mandate
        RepresentationMandate.objects.create(
            agent=agent_user.agent_profile,
            athlete=athlete,
            document=sample_mandate_document,
            verified=False,  # Not verified
            valid_from=date.today(),
        )

        # Create valid collaborator mandate
        RepresentationMandate.objects.create(
            collaborator=collaborator,
            organisation=organisations_setup["organisation"],
            document=sample_mandate_document,
            verified=True,
            valid_from=date.today() - timedelta(days=30),
        )

        api_client.force_authenticate(user=owner_user)

        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-999"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mandate" in response.data["detail"].lower()


@pytest.mark.django_db
class TestMandateMissingDetails:
    """Test detailed missing mandate information."""

    def test_missing_mandates_includes_party_details(
        self, api_client, owner_user, agent_user, athlete, organisations_setup
    ):
        """Missing mandates response includes details about which parties are missing."""
        collaborator = organisations_setup["collaborator"]
        contract = Contract.objects.create(
            organisation=organisations_setup["organisation"],
            agent=agent_user.agent_profile,
            initiated_by=collaborator,
            title="Contract for Missing Mandate Details",
            status=Contract.Status.SIGNING,
        )

        api_client.force_authenticate(user=owner_user)

        response = api_client.post(
            f"/api/contracts/{contract.id}/signing/init/",
            {"envelope_id": "test-envelope-111"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        missing = response.data["missing_mandates"]
        assert isinstance(missing, list)

        # Check agent mandate is missing
        agent_missing = any(m["party"] == "agent" for m in missing)
        org_missing = any(m["party"] == "organisation" for m in missing)

        assert agent_missing is True
        assert org_missing is True
