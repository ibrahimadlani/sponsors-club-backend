import pytest
from django.urls import reverse

from organisations.models import Collaborator, Organisation
from users.models import AgentProfile
from users.serializers import MeUpdateSerializer, RolesDataBuilder, RegisterSerializer


@pytest.mark.django_db
def test_user_manager_requires_email(user_model):
    with pytest.raises(ValueError):
        user_model.objects.create_user(email="", password="x")


@pytest.mark.django_db
def test_user_manager_account_type_defaults(user_model):
    user = user_model.objects.create_user(email="test@example.com", password="pass")
    assert user.account_type == user_model.AccountType.AGENT
    superuser = user_model.objects.create_superuser(
        email="admin@example.com", password="pass"
    )
    assert superuser.is_staff and superuser.is_superuser
    assert superuser.account_type == user_model.AccountType.AGENT


@pytest.mark.django_db
def test_user_password_hash_updates(user_model):
    user = user_model.objects.create_user(email="hash@example.com", password="initial")
    original_hash = user.password_hash
    user.set_password("newpass")
    user.save()
    assert user.password_hash != original_hash
    assert user.check_password("newpass")


@pytest.mark.django_db
def test_register_agent_success(api_client, user_model):
    url = reverse("users:register")
    payload = {
        "email": "newagent@example.com",
        "password": "pass1234",
        "account_type": "AGENT",
        "first_name": "Agent",
        "last_name": "Nouveau",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="newagent@example.com")
    assert AgentProfile.objects.filter(user=user, display_name="Agent Nouveau").exists()


@pytest.mark.django_db
def test_register_agent_uses_email_when_no_name(api_client, user_model):
    url = reverse("users:register")
    payload = {
        "email": "noname@example.com",
        "password": "pass1234",
        "account_type": "AGENT",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="noname@example.com")
    assert AgentProfile.objects.filter(
        user=user, display_name="noname@example.com"
    ).exists()


@pytest.mark.django_db
def test_register_collaborator_success(api_client, user_model):
    url = reverse("users:register")
    payload = {
        "email": "org@example.com",
        "password": "pass1234",
        "account_type": "COLLABORATOR",
        "first_name": "Org",
        "last_name": "User",
        "organisation_name": "Org Example",
        "job_title": "Founder",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="org@example.com")
    assert user.account_type == user_model.AccountType.COLLABORATOR
    assert not Organisation.objects.filter(owner=user).exists()
    assert not Collaborator.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_me_view_returns_user_data(api_client, agent_user):
    url = reverse("users:me")
    api_client.force_authenticate(user=agent_user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data["email"] == agent_user.email
    assert "agent_profile" not in response.data


@pytest.mark.django_db
def test_me_update_updates_fields(api_client, agent_user):
    url = reverse("users:me")
    api_client.force_authenticate(user=agent_user)
    payload = {
        "email": "updated@example.com",
        "first_name": "Updated",
        "last_name": "Name",
        "display_name": "Updated Agent",
    }
    response = api_client.patch(url, payload, format="json")
    assert response.status_code == 200
    agent_user.refresh_from_db()
    assert agent_user.email == "updated@example.com"
    assert agent_user.first_name == "Updated"
    assert agent_user.last_name == "Name"
    assert agent_user.agent_profile.display_name == "Updated Agent"


@pytest.mark.django_db
def test_me_update_display_name_only(api_client, agent_user):
    serializer = MeUpdateSerializer(
        agent_user,
        data={"display_name": "Solo Update"},
        partial=True,
        context={"request": None},
    )
    assert serializer.is_valid()
    serializer.save()
    agent_user.refresh_from_db()
    assert agent_user.agent_profile.display_name == "Solo Update"


@pytest.mark.django_db
def test_me_update_serializer_without_agent_profile(user_model):
    user = user_model.objects.create_user(
        email="noagent@example.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    serializer = MeUpdateSerializer(user, context={"request": None})
    data = serializer.to_representation(user)
    assert "agent_profile" not in data


@pytest.mark.django_db
def test_roles_endpoint_includes_collaborations(
    api_client, owner_user, organisations_setup
):
    url = reverse("users:me_roles")
    api_client.force_authenticate(user=owner_user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data["is_agent"] is False
    assert len(response.data["collaborations"]) == 1
    assert response.data["collaborations"][0]["organisation_id"] == str(
        organisations_setup["organisation"].id
    )


@pytest.mark.django_db
def test_roles_builder_with_agent_and_owner(agent_user, organisations_setup):
    builder = RolesDataBuilder(agent_user)
    data = builder.build()
    assert data["is_agent"] is True
    assert (
        data["agent_profile"]["display_name"] == agent_user.agent_profile.display_name
    )

    # Add collaborator membership to cover collaboration branch
    Collaborator.objects.create(
        user=agent_user,
        organisation=organisations_setup["organisation"],
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )
    data = builder.build()
    assert len(data["collaborations"]) == 1


@pytest.mark.django_db
def test_roles_builder_without_agent(user_model):
    user = user_model.objects.create_user(email="plain@example.com", password="pass")
    data = RolesDataBuilder(user).build()
    assert data["is_agent"] is False
    assert data["agent_profile"] is None
    assert data["collaborations"] == []


@pytest.mark.django_db
def test_user_manager_superuser_validation(user_model):
    with pytest.raises(ValueError):
        user_model.objects.create_superuser(
            email="invalid1@example.com",
            password="pass1234",
            is_staff=False,
        )
    with pytest.raises(ValueError):
        user_model.objects.create_superuser(
            email="invalid2@example.com",
            password="pass1234",
            is_superuser=False,
        )


@pytest.mark.django_db
def test_user_save_updates_password_hash(user_model):
    user = user_model.objects.create_user(email="save@example.com", password="pass")
    original_hash = user.password_hash
    user.password = "different-hash"
    user.save()
    assert user.password_hash == "different-hash"
    assert user.password_hash != original_hash


@pytest.mark.django_db
def test_agent_profile_str(agent_user):
    assert str(agent_user.agent_profile) == agent_user.agent_profile.display_name


@pytest.mark.django_db
def test_user_str_representation(agent_user, user_model):
    assert str(agent_user) == "Agent User"
    plain_user = user_model.objects.create_user(
        email="plain-no-name@example.com", password="pass"
    )
    assert str(plain_user) == "plain-no-name@example.com"


@pytest.mark.django_db
def test_register_serializer_representation(api_client):
    serializer = RegisterSerializer(
        data={
            "email": "rep@example.com",
            "password": "pass1234",
            "account_type": "AGENT",
            "first_name": "Rep",
            "last_name": "Agent",
        }
    )
    assert serializer.is_valid()
    user = serializer.save()
    assert user.agent_profile.display_name == "Rep Agent"
    # ensure to_representation returns expected shape
    rep = serializer.to_representation(user)
    assert rep["email"] == "rep@example.com"
    assert rep["account_type"] == "AGENT"


@pytest.mark.django_db
def test_login_and_me_flow(api_client, owner_user):
    login_url = reverse("users:login")
    response = api_client.post(
        login_url, {"email": owner_user.email, "password": "pass1234"}, format="json"
    )
    assert response.status_code == 200
    access = response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me_response = api_client.get(reverse("users:me"))
    assert me_response.status_code == 200
    assert me_response.data["email"] == owner_user.email


@pytest.mark.django_db
def test_me_entitlements_agent(api_client, agent_user, agent_subscription):
    url = reverse("users:me_entitlements")
    api_client.force_authenticate(user=agent_user)
    response = api_client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["account_type"] == agent_user.AccountType.AGENT
    features = {item["code"]: item for item in data["features"]}
    assert features["messaging_initiate"]["granted"] is True
    assert features["messaging_initiate"]["upgrade_url"]


@pytest.mark.django_db
def test_me_entitlements_collaborator(
    api_client, owner_user, organisation_subscription
):
    url = reverse("users:me_entitlements")
    api_client.force_authenticate(user=owner_user)
    response = api_client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["account_type"] == owner_user.AccountType.COLLABORATOR
    features = {item["code"]: item for item in data["features"]}
    assert features["athlete_stats_all"]["granted"] is True
    assert features["athlete_stats_all"]["recommended_plans"]
