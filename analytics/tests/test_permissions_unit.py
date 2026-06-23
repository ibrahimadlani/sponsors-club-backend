import pytest
from rest_framework.test import APIRequestFactory

from analytics.permissions import IsAgentOrStaff


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.mark.django_db
def test_is_agent_or_staff_denies_anonymous(request_factory):
    request = request_factory.get("/analytics")
    request.user = type("Anon", (), {"is_authenticated": False})()
    permission = IsAgentOrStaff()
    assert permission.has_permission(request, view=None) is False


@pytest.mark.django_db
def test_is_agent_or_staff_allows_safe_authenticated_user(request_factory, agent_user):
    request = request_factory.get("/analytics")
    request.user = agent_user
    permission = IsAgentOrStaff()
    assert permission.has_permission(request, view=None) is True


@pytest.mark.django_db
def test_is_agent_or_staff_requires_agent_profile_for_write(
    request_factory, agent_user, user_model
):
    request = request_factory.post("/analytics")
    request.user = agent_user
    permission = IsAgentOrStaff()
    assert permission.has_permission(request, view=None) is True

    non_agent = user_model.objects.create_user(
        email="collab@example.com",
        password="pass1234",
        first_name="Col",
        last_name="Laborator",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    request.user = non_agent
    assert permission.has_permission(request, view=None) is False


@pytest.mark.django_db
def test_is_agent_or_staff_allows_staff_write(request_factory, agent_user):
    request = request_factory.post("/analytics")
    agent_user.is_staff = True
    request.user = agent_user
    permission = IsAgentOrStaff()
    assert permission.has_permission(request, view=None) is True
