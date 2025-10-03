import pytest
from django.db import IntegrityError, transaction
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
        "phone_country_code": "+33",
        "phone_number": "0102030405",
        "is_self_represented": True,
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="newagent@example.com")
    assert AgentProfile.objects.filter(user=user).exists()
    assert user.agent_profile.name == "Agent Nouveau"
    assert user.phone_country_code == "+33"
    assert user.phone_number == "0102030405"
    assert user.agent_profile.is_self_represented is True


@pytest.mark.django_db
def test_register_agent_defaults_name(api_client, user_model):
    url = reverse("users:register")
    payload = {
        "email": "noname@example.com",
        "password": "pass1234",
        "account_type": "AGENT",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="noname@example.com")
    assert user.agent_profile.name == "noname@example.com"


@pytest.mark.django_db
def test_register_collaborator_success(api_client, user_model):
    url = reverse("users:register")
    payload = {
        "email": "org@example.com",
        "password": "pass1234",
        "account_type": "COLLABORATOR",
        "first_name": "Org",
        "last_name": "User",
        "phone_country_code": "+44",
        "phone_number": "2071234567",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    user = user_model.objects.get(email="org@example.com")
    assert user.account_type == user_model.AccountType.COLLABORATOR
    # Owner now references a Collaborator; querying by User must follow relation
    assert not Organisation.objects.filter(owner__user=user).exists()
    assert not Collaborator.objects.filter(user=user).exists()
    assert user.phone_country_code == "+44"
    assert user.phone_number == "2071234567"


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
        "phone_country_code": "+1",
        "phone_number": "5551112222",
        "is_self_represented": True,
    }
    response = api_client.patch(url, payload, format="json")
    assert response.status_code == 200
    agent_user.refresh_from_db()
    assert agent_user.email == "updated@example.com"
    assert agent_user.first_name == "Updated"
    assert agent_user.last_name == "Name"
    assert agent_user.agent_profile.name == "Updated Name"
    assert agent_user.agent_profile.is_self_represented is True
    assert agent_user.phone_country_code == "+1"
    assert agent_user.phone_number == "5551112222"
    assert response.data["agent_profile"]["is_self_represented"] is True
    assert response.data["agent_profile"]["name"] == "Updated Name"


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
def test_me_update_toggle_self_represented(agent_user):
    serializer = MeUpdateSerializer(
        agent_user,
        data={"is_self_represented": True},
        partial=True,
        context={"request": None},
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    agent_user.refresh_from_db()
    assert agent_user.agent_profile.is_self_represented is True


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
    assert response.data["collaboration"] == str(
        organisations_setup["organisation"].id
    )


@pytest.mark.django_db
def test_roles_builder_with_agent_and_owner(agent_user, organisations_setup):
    builder = RolesDataBuilder(agent_user)
    data = builder.build()
    assert data["is_agent"] is True
    assert data["agent_profile"]["name"] == agent_user.agent_profile.name
    assert data["agent_profile"]["is_self_represented"] is False

    # Add collaborator membership to cover collaboration branch
    Collaborator.objects.create(
        user=agent_user,
        organisation=organisations_setup["organisation"],
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )
    data = builder.build()
    assert len(data["collaborations"]) == 1
    assert data["agent_profile"]["is_self_represented"] is False
    assert "collaboration" in data


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
def test_phone_number_country_code_uniqueness(user_model):
    user_model.objects.create_user(
        email="dial@example.com",
        password="pass1234",
        phone_country_code="+33",
        phone_number="123456789",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            user_model.objects.create_user(
                email="duplicate@example.com",
                password="pass1234",
                phone_country_code="+33",
                phone_number="123456789",
            )


@pytest.mark.django_db
def test_phone_number_can_repeat_with_different_country_code(user_model):
    user_model.objects.create_user(
        email="one@example.com",
        password="pass1234",
        phone_country_code="+33",
        phone_number="123456789",
    )
    user_model.objects.create_user(
        email="two@example.com",
        password="pass1234",
        phone_country_code="+1",
        phone_number="123456789",
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
    assert str(agent_user.agent_profile) == agent_user.agent_profile.name


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
            "phone_country_code": "+49",
            "phone_number": "3012345678",
            "is_self_represented": True,
        }
    )
    assert serializer.is_valid()
    user = serializer.save()
    # ensure to_representation returns expected shape
    rep = serializer.to_representation(user)
    assert rep["phone_country_code"] == "+49"
    assert rep["phone_number"] == "3012345678"
    assert rep["email"] == "rep@example.com"
    assert rep["account_type"] == "AGENT"
    assert user.agent_profile.is_self_represented is True


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
