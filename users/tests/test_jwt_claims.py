"""Tests for custom JWT claims injected at login."""

import jwt
from django.urls import reverse
from rest_framework import status

from users.models import User, AgentProfile
from organisations.models import Organisation, Collaborator
from athletes.models import Sport, Athlete
from core import settings as django_settings


def make_agent_user(email="agent@example.com", password="pass1234", *, with_profile=True):
    user = User.objects.create_user(email=email, password=password, account_type=User.AccountType.AGENT)
    if with_profile:
        AgentProfile.objects.create(user=user, bio="", is_self_represented=False)
    return user


def login_get_access(client, email, password):
    url = reverse("users:login")
    resp = client.post(url, {"email": email, "password": password}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    return resp.data["access"]


def decode(token):
    return jwt.decode(token, django_settings.SECRET_KEY, algorithms=["HS256"])  # SimpleJWT default


def test_agent_flags_without_athlete_and_not_collaborator(api_client):
    user = make_agent_user()
    access = login_get_access(api_client, user.email, "pass1234")
    claims = decode(access)
    assert claims["role"] == "AGENT"
    assert claims["agent_has_athlete"] is False
    assert claims["collaborator_has_org"] is False


def test_agent_flags_with_athlete_and_as_collaborator(api_client):
    user = make_agent_user(email="agent2@example.com", password="pass1234")
    # Create an athlete tied to the agent
    sport = Sport.objects.create(name="Tennis")
    Athlete.objects.create(
        sport=sport,
        agent=user.agent_profile,
        full_name="Athlete One",
        birth_date="2000-01-01",
        nationality="FR",
    )
    # Link same user as collaborator on an organisation
    org = Organisation.objects.create(name="Org A")
    Collaborator.objects.create(user=user, organisation=org, role=Collaborator.Role.MEMBER, job_title="Mgr")

    access = login_get_access(api_client, user.email, "pass1234")
    claims = decode(access)
    assert claims["agent_has_athlete"] is True
    assert "collaborator_has_org" not in claims


def test_collaborator_flags_has_org(api_client):
    # Create a collaborator account
    user = User.objects.create_user(
        email="collab@example.com",
        password="pass1234",
        account_type=User.AccountType.COLLABORATOR,
    )
    org = Organisation.objects.create(name="Org B")
    Collaborator.objects.create(user=user, organisation=org, role=Collaborator.Role.MEMBER, job_title="Mgr")

    access = login_get_access(api_client, user.email, "pass1234")
    claims = decode(access)
    assert claims["role"] == "COLLABORATOR"
    assert claims["collaborator_has_org"] is True


def test_identity_fields_present(api_client):
    user = make_agent_user(email="named@example.com", password="pass1234")
    user.first_name = "Jean"
    user.last_name = "Dupont"
    user.save(update_fields=["first_name", "last_name", "updated_at"])

    access = login_get_access(api_client, user.email, "pass1234")
    claims = decode(access)
    assert claims["email"] == user.email
    assert claims["prenom"] == "Jean"
    assert claims["nom"] == "Dupont"
