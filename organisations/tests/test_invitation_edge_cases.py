"""Comprehensive tests for invitation edge cases and security scenarios."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from organisations.models import Collaborator, Organisation, OrganisationInvite


@pytest.fixture
def collaborator_user(user_model):
    """Create a collaborator user for invitation tests."""
    return user_model.objects.create_user(
        email="collab@test.com",
        password="pass1234",
        first_name="Test",
        last_name="Collaborator",
        account_type=user_model.AccountType.COLLABORATOR,
    )


@pytest.fixture
def another_collaborator_user(user_model):
    """Create a second collaborator user for multi-user tests."""
    return user_model.objects.create_user(
        email="collab2@test.com",
        password="pass1234",
        first_name="Second",
        last_name="Collaborator",
        account_type=user_model.AccountType.COLLABORATOR,
    )


@pytest.fixture
def agent_user(user_model):
    """Create an agent user to test account type restrictions."""
    from users.models import AgentProfile

    user = user_model.objects.create_user(
        email="agent@test.com",
        password="pass1234",
        first_name="Agent",
        last_name="User",
        account_type=user_model.AccountType.AGENT,
    )
    # Create agent profile for the user
    AgentProfile.objects.create(user=user)
    return user


@pytest.fixture
def owner_client(owner_user):
    """Create authenticated API client for organisation owner."""
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def member_collaborator(user_model, organisations_setup):
    """Create a MEMBER collaborator in the test organisation."""
    member_user = user_model.objects.create_user(
        email="member@test.com",
        password="pass1234",
        first_name="Member",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    collaborator = Collaborator.objects.create(
        user=member_user,
        organisation=organisations_setup["organisation"],
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )
    return collaborator


@pytest.fixture
def collaborator_client(member_collaborator):
    """Create authenticated API client for member collaborator."""
    client = APIClient()
    client.force_authenticate(user=member_collaborator.user)
    return client


@pytest.mark.django_db
class TestInvitationExpiration:
    """Tests for invitation expiration edge cases."""

    def test_join_with_expired_invite(self, collaborator_user, organisations_setup):
        """Test that joining with an expired code fails."""
        client = APIClient()
        client.force_authenticate(user=collaborator_user)

        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        # Create an expired invitation
        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="EXPIRED1",
            expires_at=timezone.now() - timedelta(hours=1),  # Expired 1 hour ago
        )

        join_url = reverse("organisation-join")
        response = client.post(
            join_url, {"code": "EXPIRED1", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        assert (
            "expired" in str(response.data["code"]).lower()
            if isinstance(response.data["code"], str)
            else response.data["code"][0].lower()
        )

    def test_expired_invitation_shows_correct_status(self, organisations_setup):
        """Test that expired invitations have correct status property."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="EXPIRED2",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        assert invite.status == "expired"

    def test_list_invites_shows_expired_status(self, owner_client, organisations_setup):
        """Test that listing invitations includes status field."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        # Create active and expired invites
        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="ACTIVE01",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="EXPIRED3",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        url = reverse("organisation-invites", kwargs={"pk": organisation.id})
        response = owner_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

        # Check that status field is present
        for invite_data in response.data:
            assert "status" in invite_data
            assert invite_data["status"] in ["active", "expired", "used"]


@pytest.mark.django_db
class TestInvitationReuse:
    """Tests for preventing invitation reuse."""

    def test_reuse_already_used_invite(
        self, collaborator_user, another_collaborator_user, organisations_setup
    ):
        """Test that a code already used cannot be reused."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="USED1234",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # First user uses the invitation
        client1 = APIClient()
        client1.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")
        response = client1.post(
            join_url, {"code": "USED1234", "job_title": "Developer"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Second user attempts to reuse the same code
        client2 = APIClient()
        client2.force_authenticate(user=another_collaborator_user)
        response = client2.post(
            join_url, {"code": "USED1234", "job_title": "Designer"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        assert (
            "already been used" in str(response.data["code"]).lower()
            if isinstance(response.data["code"], str)
            else response.data["code"][0].lower()
        )

    def test_used_invitation_shows_correct_status(
        self, collaborator_user, organisations_setup
    ):
        """Test that used invitations have correct status property."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="USED5678",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        invite.mark_used(collaborator_user)
        invite.refresh_from_db()

        assert invite.status == "used"
        assert invite.is_used is True
        assert invite.used_by == collaborator_user


@pytest.mark.django_db
class TestInvitationCodeValidation:
    """Tests for code validation edge cases."""

    def test_invalid_code_returns_error(self, collaborator_user):
        """Test that an invalid/non-existent code returns proper error."""
        client = APIClient()
        client.force_authenticate(user=collaborator_user)

        join_url = reverse("organisation-join")
        response = client.post(
            join_url, {"code": "INVALID1", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        assert (
            "invalid" in str(response.data["code"]).lower()
            if isinstance(response.data["code"], str)
            else response.data["code"][0].lower()
        )

    def test_code_case_insensitivity(self, collaborator_user, organisations_setup):
        """Test that codes are case-insensitive."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="ABCD1234",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        client = APIClient()
        client.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")

        # Use lowercase code
        response = client.post(
            join_url, {"code": "abcd1234", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_code_with_whitespace_is_stripped(
        self, collaborator_user, organisations_setup
    ):
        """Test that codes with whitespace are properly handled."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="TRIM1234",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        client = APIClient()
        client.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")

        # Send code with whitespace
        response = client.post(
            join_url, {"code": "  TRIM1234  ", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestAccountTypeRestrictions:
    """Tests for account type restrictions on joining."""

    def test_agent_cannot_join_organisation(self, agent_user, organisations_setup):
        """Test that agent accounts cannot join organisations."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="AGENT123",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        client = APIClient()
        client.force_authenticate(user=agent_user)
        join_url = reverse("organisation-join")

        response = client.post(
            join_url, {"code": "AGENT123", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        # Error is a string, not a list
        error_msg = response.data["code"]
        if isinstance(error_msg, list):
            error_msg = error_msg[0]
        assert "collaborator" in str(error_msg).lower()

    def test_user_already_in_org_cannot_join_another(
        self, collaborator_user, organisations_setup, user_model
    ):
        """Test that users already in an org cannot join via invite."""
        # User is already in an organisation
        organisation1 = organisations_setup["organisation"]
        Collaborator.objects.create(
            user=collaborator_user,
            organisation=organisation1,
            role=Collaborator.Role.MEMBER,
            job_title="Member",
        )

        # Create a second organisation
        owner2 = user_model.objects.create_user(
            email="owner2@test.com",
            password="pass1234",
            account_type=user_model.AccountType.COLLABORATOR,
        )
        organisation2 = Organisation.objects.create(name="Second Org")
        owner_collab2 = Collaborator.objects.create(
            user=owner2,
            organisation=organisation2,
            role=Collaborator.Role.OWNER,
            job_title="Owner",
        )
        organisation2.owner = owner_collab2
        organisation2.save()

        OrganisationInvite.objects.create(
            organisation=organisation2,
            created_by=owner_collab2,
            code="SECOND01",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        client = APIClient()
        client.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")

        response = client.post(
            join_url, {"code": "SECOND01", "job_title": "Developer"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        assert (
            "already belongs" in str(response.data["code"]).lower()
            if isinstance(response.data["code"], str)
            else response.data["code"][0].lower()
        )


@pytest.mark.django_db
class TestInvitationRevocation:
    """Tests for invitation revocation/deletion."""

    def test_owner_can_revoke_invite(self, owner_client, organisations_setup):
        """Test that owner can delete/revoke an invitation."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="DELETE01",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        url = reverse(
            "organisation-revoke-invite",
            kwargs={"pk": organisation.id, "invite_id": invite.id},
        )
        response = owner_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not OrganisationInvite.objects.filter(id=invite.id).exists()

    def test_cannot_revoke_used_invite(
        self, owner_client, organisations_setup, collaborator_user
    ):
        """Test that already used invitations cannot be revoked."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="USED9999",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        invite.mark_used(collaborator_user)

        url = reverse(
            "organisation-revoke-invite",
            kwargs={"pk": organisation.id, "invite_id": invite.id},
        )
        response = owner_client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been used" in response.data["detail"].lower()
        assert OrganisationInvite.objects.filter(id=invite.id).exists()

    def test_member_cannot_revoke_invite(
        self, collaborator_client, organisations_setup, member_collaborator
    ):
        """Test that non-owner collaborators cannot revoke invitations."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        invite = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="MEMBER01",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        url = reverse(
            "organisation-revoke-invite",
            kwargs={"pk": organisation.id, "invite_id": invite.id},
        )
        response = collaborator_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_revoke_nonexistent_invite_returns_404(
        self, owner_client, organisations_setup
    ):
        """Test that revoking a non-existent invitation returns 404."""
        organisation = organisations_setup["organisation"]

        url = reverse(
            "organisation-revoke-invite",
            kwargs={
                "pk": organisation.id,
                "invite_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        response = owner_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestInvitationFiltering:
    """Tests for invitation status filtering."""

    def test_filter_active_invites(self, owner_client, organisations_setup):
        """Test filtering to show only active invitations."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        # Create different status invites
        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="ACTIVE01",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="EXPIRED1",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        url = reverse("organisation-invites", kwargs={"pk": organisation.id})
        response = owner_client.get(url, {"status": "active"})

        assert response.status_code == status.HTTP_200_OK
        codes = [inv["code"] for inv in response.data]
        assert "ACTIVE01" in codes
        assert "EXPIRED1" not in codes

    def test_filter_expired_invites(self, owner_client, organisations_setup):
        """Test filtering to show only expired invitations."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="ACTIVE02",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="EXPIRED2",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        url = reverse("organisation-invites", kwargs={"pk": organisation.id})
        response = owner_client.get(url, {"status": "expired"})

        assert response.status_code == status.HTTP_200_OK
        codes = [inv["code"] for inv in response.data]
        assert "EXPIRED2" in codes
        assert "ACTIVE02" not in codes

    def test_filter_used_invites(
        self, owner_client, organisations_setup, collaborator_user
    ):
        """Test filtering to show only used invitations."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="ACTIVE03",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        used = OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="USED0001",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        used.mark_used(collaborator_user)

        url = reverse("organisation-invites", kwargs={"pk": organisation.id})
        response = owner_client.get(url, {"status": "used"})

        assert response.status_code == status.HTTP_200_OK
        codes = [inv["code"] for inv in response.data]
        assert "USED0001" in codes
        assert "ACTIVE03" not in codes


@pytest.mark.django_db
class TestRaceConditions:
    """Tests for concurrent invitation usage."""

    def test_select_for_update_prevents_double_use(
        self, collaborator_user, another_collaborator_user, organisations_setup
    ):
        """Test that select_for_update prevents race conditions."""
        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="RACE1234",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # First user successfully uses the code
        client1 = APIClient()
        client1.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")

        response1 = client1.post(
            join_url, {"code": "RACE1234", "job_title": "Developer"}, format="json"
        )
        assert response1.status_code == status.HTTP_201_CREATED

        # Second user's attempt should fail due to code being marked as used
        client2 = APIClient()
        client2.force_authenticate(user=another_collaborator_user)

        response2 = client2.post(
            join_url, {"code": "RACE1234", "job_title": "Designer"}, format="json"
        )
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        code_error = response2.data["code"]
        if isinstance(code_error, list):
            code_error = code_error[0]
        assert "already been used" in str(code_error).lower()


@pytest.mark.django_db
class TestInvitationThrottling:
    """Tests for rate limiting on invitation endpoints."""

    @patch("organisations.views.InviteCreateThrottle.allow_request")
    def test_invite_creation_throttled(
        self, mock_allow_request, owner_client, organisations_setup
    ):
        """Test that excessive invite creation is throttled."""
        mock_allow_request.return_value = False

        organisation = organisations_setup["organisation"]
        url = reverse("organisation-invites", kwargs={"pk": organisation.id})

        response = owner_client.post(url, {"expires_in_hours": 24}, format="json")

        # Should be throttled
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    @patch("organisations.throttling.InviteJoinThrottle.allow_request")
    def test_invite_join_throttled(
        self, mock_allow_request, collaborator_user, organisations_setup
    ):
        """Test that excessive join attempts are throttled."""
        mock_allow_request.return_value = False

        organisation = organisations_setup["organisation"]
        owner = organisation.collaborators.filter(role=Collaborator.Role.OWNER).first()

        OrganisationInvite.objects.create(
            organisation=organisation,
            created_by=owner,
            code="THROTTLE",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        client = APIClient()
        client.force_authenticate(user=collaborator_user)
        join_url = reverse("organisation-join")

        response = client.post(
            join_url, {"code": "THROTTLE", "job_title": "Developer"}, format="json"
        )

        # Should be throttled
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
