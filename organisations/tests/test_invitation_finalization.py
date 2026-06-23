"""Tests for invitation audit logging and email notifications."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from organisations.models import (
    InvitationAuditLog,
    OrganisationInvite,
)
from organisations.services import (
    get_client_ip,
    log_invitation_action,
    send_invitation_accepted_email,
    send_invitation_created_email,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def collaborator_user(user_model):
    return user_model.objects.create_user(
        email="joiner@test.com",
        password="pass1234",
        first_name="Jane",
        last_name="Joiner",
        account_type=user_model.AccountType.COLLABORATOR,
    )


@pytest.fixture
def joiner_client(collaborator_user):
    client = APIClient()
    client.force_authenticate(user=collaborator_user)
    return client


@pytest.fixture
def owner_client(owner_user):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def active_invite(organisations_setup):
    org = organisations_setup["organisation"]
    owner_collab = organisations_setup["collaborator"]
    return OrganisationInvite.objects.create(
        organisation=org,
        created_by=owner_collab,
        code=OrganisationInvite.generate_code(),
        expires_at=timezone.now() + timedelta(hours=24),
    )


# ---------------------------------------------------------------------------
# get_client_ip() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetClientIp:
    def test_returns_remote_addr_when_no_forwarded_header(self, factory):
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
        assert get_client_ip(request) == "10.0.0.1"

    def test_returns_leftmost_forwarded_for_ip(self, factory):
        request = factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 5.6.7.8, 9.10.11.12"
        assert get_client_ip(request) == "1.2.3.4"

    def test_returns_none_when_no_ip_available(self, factory):
        request = factory.get("/")
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
        request.META.pop("REMOTE_ADDR", None)
        assert get_client_ip(request) is None

    def test_strips_whitespace_from_forwarded_for(self, factory):
        request = factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "  203.0.113.5  , 10.0.0.1"
        assert get_client_ip(request) == "203.0.113.5"


# ---------------------------------------------------------------------------
# log_invitation_action() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLogInvitationAction:
    def test_creates_log_entry_without_request(self, active_invite):
        log = log_invitation_action(active_invite, InvitationAuditLog.Action.CREATED)

        assert log.invite == active_invite
        assert log.action == InvitationAuditLog.Action.CREATED
        assert log.actor is None
        assert log.ip_address is None
        assert log.user_agent == ""

    def test_creates_log_entry_with_request_ip_and_ua(
        self, active_invite, factory, owner_user
    ):
        request = factory.get(
            "/",
            HTTP_USER_AGENT="TestBrowser/1.0",
            REMOTE_ADDR="192.168.1.10",
        )
        request.user = owner_user

        log = log_invitation_action(
            active_invite, InvitationAuditLog.Action.CREATED, request=request
        )

        assert log.ip_address == "192.168.1.10"
        assert log.user_agent == "TestBrowser/1.0"
        assert log.actor == owner_user

    def test_extracts_actor_from_authenticated_request(
        self, active_invite, factory, owner_user
    ):
        request = factory.get("/")
        request.user = owner_user

        log = log_invitation_action(
            active_invite, InvitationAuditLog.Action.REVOKED, request=request
        )

        assert log.actor == owner_user

    def test_explicit_actor_overrides_request_user(
        self, active_invite, factory, owner_user, collaborator_user
    ):
        request = factory.get("/")
        request.user = owner_user

        log = log_invitation_action(
            active_invite,
            InvitationAuditLog.Action.ACCEPTED,
            request=request,
            actor=collaborator_user,
        )

        assert log.actor == collaborator_user

    def test_truncates_user_agent_to_512_chars(
        self, active_invite, factory, owner_user
    ):
        long_ua = "A" * 600
        request = factory.get("/", HTTP_USER_AGENT=long_ua)
        request.user = owner_user

        log = log_invitation_action(
            active_invite, InvitationAuditLog.Action.CREATED, request=request
        )

        assert len(log.user_agent) == 512

    def test_respects_x_forwarded_for_header(self, active_invite, factory, owner_user):
        request = factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="203.0.113.99, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        request.user = owner_user

        log = log_invitation_action(
            active_invite, InvitationAuditLog.Action.CREATED, request=request
        )

        assert log.ip_address == "203.0.113.99"

    def test_all_action_choices_are_valid(self, active_invite):
        actions = [
            InvitationAuditLog.Action.CREATED,
            InvitationAuditLog.Action.ACCEPTED,
            InvitationAuditLog.Action.REVOKED,
            InvitationAuditLog.Action.EXPIRED,
        ]
        for action in actions:
            log = log_invitation_action(active_invite, action)
            assert log.action == action

    def test_log_saved_to_database(self, active_invite):
        log = log_invitation_action(active_invite, InvitationAuditLog.Action.CREATED)
        assert InvitationAuditLog.objects.filter(pk=log.pk).exists()

    def test_audit_log_related_to_invite(self, active_invite):
        log_invitation_action(active_invite, InvitationAuditLog.Action.CREATED)
        assert active_invite.audit_logs.count() == 1


# ---------------------------------------------------------------------------
# send_invitation_created_email() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSendInvitationCreatedEmail:
    def test_calls_send_email_with_correct_subject(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_created_email(active_invite, "recipient@test.com")

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "Test Org" in msg.subject
        assert "Sponsors Club" in msg.subject

    def test_sends_to_recipient_address(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_created_email(active_invite, "recipient@test.com")

        msg = mock_send.call_args[0][0]
        assert msg.to_addresses == ["recipient@test.com"]

    def test_includes_invite_code_in_bodies(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_created_email(active_invite, "recipient@test.com")

        msg = mock_send.call_args[0][0]
        assert active_invite.code in msg.text_body
        assert active_invite.code in msg.html_body

    def test_uses_invitation_created_tag(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_created_email(active_invite, "recipient@test.com")

        msg = mock_send.call_args[0][0]
        assert ("template", "invitation-created") in msg.tags

    def test_silently_catches_email_delivery_error(self, active_invite):
        from core.emails import EmailDeliveryError

        with patch("core.emails.send_email", side_effect=EmailDeliveryError("fail")):
            # Must not raise
            send_invitation_created_email(active_invite, "recipient@test.com")


# ---------------------------------------------------------------------------
# send_invitation_accepted_email() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSendInvitationAcceptedEmail:
    def test_sends_to_owner_email(self, active_invite, owner_user):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_accepted_email(active_invite, "newmember@test.com")

        msg = mock_send.call_args[0][0]
        assert msg.to_addresses == [owner_user.email]

    def test_subject_contains_organisation_name(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_accepted_email(active_invite, "newmember@test.com")

        msg = mock_send.call_args[0][0]
        assert "Test Org" in msg.subject

    def test_includes_new_member_email_in_body(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_accepted_email(active_invite, "newmember@test.com")

        msg = mock_send.call_args[0][0]
        assert "newmember@test.com" in msg.text_body
        assert "newmember@test.com" in msg.html_body

    def test_uses_invitation_accepted_tag(self, active_invite):
        with patch("core.emails.send_email") as mock_send:
            send_invitation_accepted_email(active_invite, "newmember@test.com")

        msg = mock_send.call_args[0][0]
        assert ("template", "invitation-accepted") in msg.tags

    def test_silently_catches_email_delivery_error(self, active_invite):
        from core.emails import EmailDeliveryError

        with patch("core.emails.send_email", side_effect=EmailDeliveryError("fail")):
            send_invitation_accepted_email(active_invite, "newmember@test.com")


# ---------------------------------------------------------------------------
# API integration — invite creation (views.py hook)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInviteCreationAuditLog:
    def _create_invite(self, client, org, payload=None):
        url = reverse("organisation-invites", kwargs={"pk": str(org.id)})
        return client.post(url, payload or {}, format="json")

    def test_creates_audit_log_on_invite_creation(
        self, owner_client, organisations_setup
    ):
        org = organisations_setup["organisation"]
        with patch("organisations.services.send_invitation_created_email"):
            response = self._create_invite(owner_client, org)

        assert response.status_code == status.HTTP_201_CREATED
        invite = OrganisationInvite.objects.get(code=response.data["code"])
        assert InvitationAuditLog.objects.filter(
            invite=invite, action=InvitationAuditLog.Action.CREATED
        ).exists()

    def test_sends_invitation_email_when_target_email_provided(
        self, owner_client, organisations_setup
    ):
        org = organisations_setup["organisation"]
        with patch(
            "organisations.services.send_invitation_created_email"
        ) as mock_email:
            response = self._create_invite(
                owner_client, org, {"target_email": "vip@example.com"}
            )

        assert response.status_code == status.HTTP_201_CREATED
        mock_email.assert_called_once()
        _, called_email = mock_email.call_args[0]
        assert called_email == "vip@example.com"

    def test_no_email_sent_when_target_email_absent(
        self, owner_client, organisations_setup
    ):
        org = organisations_setup["organisation"]
        with patch(
            "organisations.services.send_invitation_created_email"
        ) as mock_email:
            response = self._create_invite(owner_client, org)

        assert response.status_code == status.HTTP_201_CREATED
        mock_email.assert_not_called()

    def test_invite_creation_succeeds_even_if_email_delivery_fails(
        self, owner_client, organisations_setup
    ):
        from core.emails import EmailDeliveryError

        org = organisations_setup["organisation"]
        with patch("core.emails.send_email", side_effect=EmailDeliveryError("boom")):
            response = self._create_invite(
                owner_client, org, {"target_email": "vip@example.com"}
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert OrganisationInvite.objects.filter(code=response.data["code"]).exists()

    def test_target_email_stored_on_invite_record(
        self, owner_client, organisations_setup
    ):
        org = organisations_setup["organisation"]
        with patch("organisations.services.send_invitation_created_email"):
            response = self._create_invite(
                owner_client, org, {"target_email": "stored@example.com"}
            )

        assert response.status_code == status.HTTP_201_CREATED
        invite = OrganisationInvite.objects.get(code=response.data["code"])
        assert invite.target_email == "stored@example.com"

    def test_target_email_exposed_in_response(self, owner_client, organisations_setup):
        org = organisations_setup["organisation"]
        with patch("organisations.services.send_invitation_created_email"):
            response = self._create_invite(
                owner_client, org, {"target_email": "exposed@example.com"}
            )

        assert response.data["target_email"] == "exposed@example.com"


# ---------------------------------------------------------------------------
# API integration — invite revocation (views.py hook)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInviteRevocationAuditLog:
    def test_calls_log_action_with_revoked_on_delete(
        self, owner_client, organisations_setup, active_invite
    ):
        """Views calls log_invitation_action(REVOKED) before deleting the invite."""
        org = organisations_setup["organisation"]
        url = reverse(
            "organisation-revoke-invite",
            kwargs={"pk": str(org.id), "invite_id": str(active_invite.id)},
        )

        with patch("organisations.services.log_invitation_action") as mock_log:
            response = owner_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_log.assert_called_once()
        _, called_action = mock_log.call_args[0]
        assert called_action == InvitationAuditLog.Action.REVOKED

    def test_invite_deleted_after_revocation(
        self, owner_client, organisations_setup, active_invite
    ):
        org = organisations_setup["organisation"]
        url = reverse(
            "organisation-revoke-invite",
            kwargs={"pk": str(org.id), "invite_id": str(active_invite.id)},
        )

        response = owner_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not OrganisationInvite.objects.filter(id=active_invite.id).exists()


# ---------------------------------------------------------------------------
# API integration — invite acceptance (serializers.py hook)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInviteAcceptanceAuditLog:
    def _join(self, client, code):
        url = reverse("organisation-join")
        return client.post(url, {"code": code}, format="json")

    def test_creates_audit_log_on_join(
        self, joiner_client, collaborator_user, active_invite
    ):
        with patch("organisations.services.send_invitation_accepted_email"):
            response = self._join(joiner_client, active_invite.code)

        assert response.status_code == status.HTTP_201_CREATED
        assert InvitationAuditLog.objects.filter(
            invite=active_invite, action=InvitationAuditLog.Action.ACCEPTED
        ).exists()

    def test_sends_accepted_email_to_owner_on_join(
        self, joiner_client, active_invite, owner_user
    ):
        with patch(
            "organisations.services.send_invitation_accepted_email"
        ) as mock_email:
            response = self._join(joiner_client, active_invite.code)

        assert response.status_code == status.HTTP_201_CREATED
        mock_email.assert_called_once()
        _, called_email = mock_email.call_args[0]
        assert called_email == joiner_client.handler._force_user.email

    def test_join_succeeds_even_if_accepted_email_fails(
        self, joiner_client, active_invite
    ):
        from core.emails import EmailDeliveryError

        with patch("core.emails.send_email", side_effect=EmailDeliveryError("down")):
            response = self._join(joiner_client, active_invite.code)

        assert response.status_code == status.HTTP_201_CREATED

    def test_audit_log_actor_is_joining_user(
        self, joiner_client, collaborator_user, active_invite
    ):
        with patch("organisations.services.send_invitation_accepted_email"):
            self._join(joiner_client, active_invite.code)

        log = InvitationAuditLog.objects.get(
            invite=active_invite, action=InvitationAuditLog.Action.ACCEPTED
        )
        assert log.actor == collaborator_user
