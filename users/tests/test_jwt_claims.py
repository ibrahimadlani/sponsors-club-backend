"""Tests for rich JWT claims injected at login."""

from decimal import Decimal

import pytest

import jwt
from django.urls import reverse
from rest_framework import status

from athletes.models import Athlete, Sport
from contracts.models import Contract
from django.conf import settings as django_settings
from follows.models import Follow
from notifications.models import Notification
from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User


def login_get_access(client, email, password):
    url = reverse("users:login")
    resp = client.post(url, {"email": email, "password": password}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    return resp.data["access"]


def decode(token):
    return jwt.decode(
        token, django_settings.SECRET_KEY, algorithms=["HS256"]
    )  # SimpleJWT default


pytestmark = pytest.mark.django_db


def test_agent_jwt_payload_enriched(api_client, agent_user, agent_subscription):
    agent_user.first_name = "Ada"
    agent_user.last_name = "Lovelace"
    agent_user.save(update_fields=["first_name", "last_name", "updated_at"])
    agent_user.agent_profile.bio = "Representing elite athletes across Europe"
    agent_user.agent_profile.save(update_fields=["bio", "updated_at"])

    sport = Sport.objects.create(name="Football")
    Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Julien Dupont",
        birth_date="1999-01-01",
        nationality="FR",
        followers_count_cached=153000,
        engagement_rate_cached=Decimal("3.20"),
    )
    Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Léa Bernard",
        birth_date="2001-02-02",
        nationality="FR",
        followers_count_cached=88000,
        engagement_rate_cached=Decimal("4.10"),
    )

    organisation = Organisation.objects.create(name="Collab Org")
    Collaborator.objects.create(
        user=agent_user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Partnership Lead",
    )

    access = login_get_access(api_client, agent_user.email, "pass1234")
    claims = decode(access)

    assert claims["sub"] == str(agent_user.id)
    assert claims["email"] == agent_user.email
    assert claims["first_name"] == "Ada"
    assert claims["last_name"] == "Lovelace"
    assert claims["role"] == User.AccountType.AGENT

    profile = claims["profile"]
    assert profile["agent_profile_id"] == str(agent_user.agent_profile.id)
    assert profile["display_name"] == "Ada Lovelace"
    assert profile["bio"] == "Representing elite athletes across Europe"
    assert profile["athletes_count"] == 2
    assert {athlete["full_name"] for athlete in profile["athletes"]} == {
        "Julien Dupont",
        "Léa Bernard",
    }

    stats = claims["stats"]
    assert stats["followers_total"] == 241000
    assert stats["avg_engagement_rate"] == pytest.approx(3.65, rel=1e-3)
    assert stats["most_followed_athlete"]["name"] == "Julien Dupont"

    plan = claims["plan"]
    assert plan["code"] == agent_subscription.plan.code
    assert plan["price"] == float(agent_subscription.plan.price)
    assert plan["max_athletes"] == agent_subscription.plan.max_athletes
    assert plan["features"]["messaging_tier"] == "pro_plus"

    entitlements = claims["entitlements"]
    assert entitlements["messaging_initiate"]["granted"] is True
    assert entitlements["contract_management"]["granted"] is True
    assert entitlements["contract_management"]["upgrade_suggestion"] is None

    onboarding = claims["onboarding"]
    assert onboarding["needs_athlete"] is False
    assert onboarding["has_active_subscription"] is True
    assert onboarding["has_collaboration"] is True

    assert claims["permissions"] == {"is_staff": False, "is_superuser": False}
    meta = claims["meta"]
    expected_api_version = getattr(django_settings, "API_VERSION", "v1")
    expected_env = getattr(
        django_settings,
        "APP_ENV",
        "development" if getattr(django_settings, "DEBUG", False) else "production",
    )
    assert meta["api_version"] == expected_api_version
    assert meta["app_env"] == expected_env
    assert meta["issued_at"].endswith("Z")
    assert meta["expires_at"].endswith("Z")


def test_collaborator_jwt_payload_enriched(api_client, organisations_setup):
    owner = organisations_setup["owner"]
    collaborator = organisations_setup["collaborator"]
    organisation = organisations_setup["organisation"]
    subscription = organisations_setup["subscription"]

    agent_user = User.objects.create_user(
        email="agent-collab@test.com",
        password="pass1234",
        account_type=User.AccountType.AGENT,
    )
    agent_profile = AgentProfile.objects.create(user=agent_user)

    sport = Sport.objects.create(name="Basketball")
    athlete_one = Athlete.objects.create(
        sport=sport,
        agent=agent_profile,
        full_name="Jordan Elite",
        birth_date="1995-05-05",
        nationality="US",
        followers_count_cached=50000,
        engagement_rate_cached=Decimal("5.00"),
    )
    athlete_two = Athlete.objects.create(
        sport=sport,
        agent=agent_profile,
        full_name="Skylar Rise",
        birth_date="1998-08-08",
        nationality="US",
        followers_count_cached=42000,
        engagement_rate_cached=Decimal("4.30"),
    )

    Follow.objects.create(collaborator=collaborator, athlete=athlete_one)
    Follow.objects.create(collaborator=collaborator, athlete=athlete_two)

    Contract.objects.create(
        organisation=organisation,
        agent=agent_profile,
        initiated_by=collaborator,
        status=Contract.Status.ACTIVE,
        title="Global Kit Deal",
    )
    Contract.objects.create(
        organisation=organisation,
        agent=agent_profile,
        initiated_by=collaborator,
        status=Contract.Status.NEGOTIATION,
        title="Regional Activation",
    )

    Notification.objects.create(
        user=owner,
        type=Notification.Type.NEW_MESSAGE,
        payload={},
        is_read=False,
    )
    Notification.objects.create(
        user=owner,
        type=Notification.Type.CONTRACT_STATUS,
        payload={},
        is_read=False,
    )
    Notification.objects.create(
        user=owner,
        type=Notification.Type.STAT_UPDATE,
        payload={},
        is_read=True,
    )

    access = login_get_access(api_client, owner.email, "pass1234")
    claims = decode(access)

    assert claims["role"] == User.AccountType.COLLABORATOR
    profile = claims["profile"]
    assert profile["collaborator_ids"] == [str(collaborator.id)]
    assert profile["organisations_count"] == 1
    assert profile["is_owner"] is True
    assert profile["is_member"] is False
    assert profile["primary_collaboration"]["organisation_name"] == organisation.name
    assert profile["primary_collaboration"]["role"] == Collaborator.Role.OWNER

    plan = claims["plan"]
    assert plan["code"] == subscription.plan.code
    assert plan["price"] == float(subscription.plan.price)
    assert plan["max_collaborators"] == subscription.plan.max_collaborators
    assert plan["features"]["contract_tools"] == "enabled"
    assert plan["features"]["max_follows"] >= 10

    entitlements = claims["entitlements"]
    assert entitlements["notification_center"]["granted"] is True
    assert entitlements["follow_slots"]["limit"] >= 10

    onboarding = claims["onboarding"]
    assert onboarding["needs_organisation"] is False
    assert onboarding["has_active_subscription"] is True

    activity = claims["activity"]
    assert activity["follows_count"] == 2
    assert activity["active_contracts_count"] == 1
    assert activity["pending_contracts_count"] == 1
    assert activity["unread_notifications"] == 2

    meta = claims["meta"]
    expected_api_version = getattr(django_settings, "API_VERSION", "v1")
    expected_env = getattr(
        django_settings,
        "APP_ENV",
        "development" if getattr(django_settings, "DEBUG", False) else "production",
    )
    assert meta["api_version"] == expected_api_version
    assert meta["app_env"] == expected_env
