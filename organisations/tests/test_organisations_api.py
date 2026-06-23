"""Tests for organisation models, serializers, permissions and API views."""

import uuid
from datetime import timedelta

import pytest
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.pagination import PageNumberPagination

from organisations.models import Collaborator, Organisation, OrganisationInvite
from organisations.permissions import (
    IsAuthenticatedCollaborator,
    IsOrganisationCreator,
    IsOrganisationOwner,
)
from organisations.serializers import (
    CollaboratorCreateSerializer,
    CollaboratorSerializer,
    OrganisationCreateSerializer,
    OrganisationInviteCreateSerializer,
    OrganisationListFilter,
    OrganisationSerializer,
)


@pytest.fixture
def factory():
    """Return a DRF request factory for serializer unit tests."""
    return APIRequestFactory()


@pytest.fixture
def owner_client(owner_user):
    """Return an API client authenticated as the organisation owner."""
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def staff_user(user_model):
    return user_model.objects.create_user(
        email="staff@test.com",
        password="pass1234",
        first_name="Staff",
        last_name="User",
        is_staff=True,
        account_type=user_model.AccountType.COLLABORATOR,
    )


@pytest.fixture
def staff_client(staff_user):
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def collaborator_user(user_model):
    """Create and return a collaborator account for membership tests."""
    user = user_model.objects.create_user(
        email="collab@test.com",
        password="pass1234",
        first_name="Collab",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    return user


@pytest.fixture
def collaborator_client(collaborator_user):
    """Return an API client authenticated as a collaborator-level user."""
    client = APIClient()
    client.force_authenticate(user=collaborator_user)
    return client


@pytest.fixture
def organisation(organisations_setup):
    """Provide the default organisation instance from the shared setup."""
    return organisations_setup["organisation"]


@pytest.fixture
def member_collaborator(collaborator_user, organisation):
    """Return a collaborator with member role attached to the organisation."""
    return Collaborator.objects.create(
        user=collaborator_user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Member",
    )


@pytest.mark.django_db
def test_organisation_str(organisation):
    """Organisation string representation returns its name."""
    assert str(organisation) == organisation.name


@pytest.mark.django_db
def test_organisation_get_owner_id(organisations_setup):
    """Return the owner collaborator identifier when present."""
    organisation = organisations_setup["organisation"]
    collaborator = organisations_setup["collaborator"]
    # Owner field now points to Collaborator; compare nested user
    assert organisation.owner.user == collaborator.user
    assert organisation.get_owner_id() == collaborator.id
    collaborator.delete()
    assert organisation.get_owner_id() is None


@pytest.mark.django_db
def test_collaborator_str(organisations_setup):
    """Collaborator string displays user, organisation and role."""
    collaborator = organisations_setup["collaborator"]
    expected = (
        f"{collaborator.user} - {collaborator.organisation.name} ({collaborator.role})"
    )
    assert str(collaborator) == expected


@pytest.mark.django_db
def test_organisation_serializer_owner_field(organisations_setup):
    """Organisation serializer exposes the owner collaborator id."""
    organisation = organisations_setup["organisation"]
    data = OrganisationSerializer(organisation).data
    assert data["owner_id"] == str(organisations_setup["collaborator"].id)


@pytest.mark.django_db
def test_organisation_create_serializer(factory, user_model):
    """Creating an organisation persists owner collaborator membership."""
    user = user_model.objects.create_user(
        email="creator@test.com",
        password="pass1234",
        first_name="Creator",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    request = factory.post("/api/organisations/")
    request.user = user
    serializer = OrganisationCreateSerializer(
        data={
            "name": "Created Org",
            "type": Organisation.Type.STARTUP,
            "industry": "Tech",
            "description": "New organisation",
            "website_url": "https://example.com",
            "email_contact": "hello@example.com",
            "phone_contact": "+33123456789",
            "address_city": "Paris",
            "address_country": "FR",
            "address_postal_code": "75000",
            "social_links": {"linkedin": "https://linkedin.com/company/example"},
            "founded_year": 2020,
            "employees_count": 12,
            "budget_range": "10k-100k",
            "sponsoring_focus": ["sports collectifs"],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    organisation = serializer.save()
    user.refresh_from_db()
    assert user.account_type == user_model.AccountType.COLLABORATOR
    assert organisation.owner.user == user
    assert Collaborator.objects.filter(
        user=user, organisation=organisation, role=Collaborator.Role.OWNER
    ).exists()


@pytest.mark.django_db
def test_organisation_create_serializer_rejects_agent(factory, user_model):
    """Serializer validation fails for agent accounts."""
    user = user_model.objects.create_user(
        email="agent-creator@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    request = factory.post("/api/organisations/")
    request.user = user
    serializer = OrganisationCreateSerializer(
        data={
            "name": "Blocked Org",
            "type": Organisation.Type.BRAND,
            "industry": "Tech",
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(serializers.ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_organisation_create_serializer_rejects_existing_collaborator(
    factory, organisations_setup
):
    """Serializer validation fails for collaborators already in an organisation."""
    request = factory.post("/api/organisations/")
    request.user = organisations_setup["owner"]
    serializer = OrganisationCreateSerializer(
        data={
            "name": "Blocked Org",
            "type": Organisation.Type.BRAND,
            "industry": "Tech",
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(serializers.ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_collaborator_serializer_fields(organisations_setup):
    """Collaborator serializer exposes related user metadata."""
    collaborator = organisations_setup["collaborator"]
    data = CollaboratorSerializer(collaborator).data
    assert data["user_email"] == collaborator.user.email
    assert data["user_full_name"] == str(collaborator.user)
    assert data["role"] == collaborator.role


@pytest.mark.django_db
def test_collaborator_create_serializer_validate_role(organisation):
    """Reject invitations that attempt to promote to owner via serializer."""
    serializer = CollaboratorCreateSerializer(
        data={
            "email": "x@test.com",
            "role": Collaborator.Role.OWNER,
            "job_title": "Owner",
        },
        context={"organisation": organisation},
    )
    assert not serializer.is_valid()
    assert "role" in serializer.errors


@pytest.mark.django_db
def test_organisation_deleted_when_owner_removed(organisations_setup):
    """Organisation cascades when the owner user is deleted."""
    organisation = organisations_setup["organisation"]
    owner = organisation.owner
    owner.delete()
    assert not Organisation.objects.filter(id=organisation.id).exists()


@pytest.mark.django_db
def test_collaborator_create_serializer_validate_duplicate(organisations_setup):
    """Ensure duplicate collaborator invitations are rejected."""
    organisation = organisations_setup["organisation"]
    existing_email = organisations_setup["collaborator"].user.email
    serializer = CollaboratorCreateSerializer(
        data={
            "email": existing_email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        context={"organisation": organisation},
    )
    assert not serializer.is_valid()
    assert "email" in serializer.errors


@pytest.mark.django_db
def test_collaborator_create_serializer_missing_user(organisation):
    """Raise a validation error when the invitee does not exist."""
    serializer = CollaboratorCreateSerializer(
        data={
            "email": "missing@test.com",
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        context={"organisation": organisation},
    )
    assert serializer.is_valid()
    with pytest.raises(serializers.ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_collaborator_create_serializer_success(organisation, user_model):
    """Successfully add an existing collaborator account to the organisation."""
    invitee = user_model.objects.create_user(
        email="invitee@test.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    serializer = CollaboratorCreateSerializer(
        data={
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        context={"organisation": organisation},
    )
    assert serializer.is_valid(), serializer.errors
    collaborator = serializer.save()
    assert collaborator.user == invitee
    assert collaborator.organisation == organisation


@pytest.mark.django_db
def test_collaborator_create_serializer_rejects_agent_accounts(
    organisation, user_model
):
    """Agent accounts cannot be invited to collaborate with an organisation."""
    invitee = user_model.objects.create_user(
        email="agent-invite@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    serializer = CollaboratorCreateSerializer(
        data={
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        context={"organisation": organisation},
    )
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(serializers.ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_organisation_list_filter_validation():
    """Organisation list filter accepts optional query parameters."""
    serializer = OrganisationListFilter(
        data={
            "type": Organisation.Type.BRAND,
            "industry": "Tech",
            "address_country": "FR",
        }
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_is_authenticated_collaborator_permission(
    factory, owner_user, organisation, user_model
):
    """Permission grants access only to authenticated collaborators."""
    permission = IsAuthenticatedCollaborator()
    request = factory.get("/")
    request.user = owner_user

    class Dummy:
        pass

    view_without_org = Dummy()
    assert not permission.has_permission(request, view_without_org)

    outsider = user_model.objects.create_user(
        email="outsider@test.com", password="pass1234"
    )
    view = Dummy()
    view.organisation = organisation
    request.user = outsider
    assert not permission.has_permission(request, view)

    request.user = owner_user
    assert permission.has_permission(request, view)


@pytest.mark.django_db
def test_is_organisation_owner_permission(
    factory, owner_user, organisation, member_collaborator
):
    """Permission ensures only owners may perform privileged actions."""
    permission = IsOrganisationOwner()

    class Dummy:
        pass

    view = Dummy()
    view.organisation = organisation
    view_without_org = Dummy()

    request = factory.get("/")
    request.user = member_collaborator.user
    assert not permission.has_permission(request, view)

    request.user = owner_user
    assert permission.has_permission(request, view)

    request.user = owner_user
    assert not permission.has_permission(request, view_without_org)


@pytest.mark.django_db
def test_is_organisation_creator_permission(
    factory, owner_user, collaborator_user, agent_user, staff_user
):
    """Permission grants access to staff or collaborators without an organisation."""
    permission = IsOrganisationCreator()
    request = factory.get("/")

    request.user = collaborator_user
    assert permission.has_permission(request, None)

    request.user = owner_user
    assert not permission.has_permission(request, None)

    request.user = agent_user
    assert not permission.has_permission(request, None)

    request.user = staff_user
    assert permission.has_permission(request, None)


@pytest.mark.django_db
def test_organisation_list_and_filter(staff_client, organisation):
    """List endpoint supports filtering by organisation attributes for staff."""
    list_url = reverse("organisation-list")
    response = staff_client.get(list_url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) >= 1

    Organisation.objects.create(
        owner=organisation.owner,
        name="Filtered Org",
        type=Organisation.Type.BRAND,
        industry="Sportswear",
        address_country="FR",
    )
    filtered = staff_client.get(list_url, {"industry": "Sportswear"})
    assert filtered.status_code == status.HTTP_200_OK
    assert len(filtered.data) == 1
    assert filtered.data[0]["name"] == "Filtered Org"


@pytest.mark.django_db
def test_organisation_list_forbidden_for_non_staff(owner_client, agent_user):
    """Non-staff users are not allowed to list organisations."""
    list_url = reverse("organisation-list")
    response = owner_client.get(list_url)
    assert response.status_code == status.HTTP_403_FORBIDDEN

    client = APIClient()
    client.force_authenticate(user=agent_user)
    response = client.get(list_url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_organisation_list_pagination(staff_client, organisation):
    """List endpoint applies pagination when configured on the viewset."""

    class SingleItemPagination(PageNumberPagination):
        page_size = 1

    Organisation.objects.create(
        owner=organisation.owner,
        name="Second Org",
        type=Organisation.Type.BRAND,
        industry="Tech",
        address_country="FR",
    )

    list_url = reverse("organisation-list")
    with patch(
        "organisations.views.OrganisationViewSet.pagination_class", SingleItemPagination
    ):
        response = staff_client.get(list_url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_organisation_retrieve(owner_client, organisation):
    """Retrieve endpoint returns organisation details for owners."""
    detail_url = reverse("organisation-detail", kwargs={"pk": organisation.id})
    response = owner_client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == organisation.name


@pytest.mark.django_db
def test_organisation_retrieve_forbidden_for_agent(agent_user, organisation):
    """Agents cannot retrieve organisation details."""
    client = APIClient()
    client.force_authenticate(user=agent_user)
    detail_url = reverse("organisation-detail", kwargs={"pk": organisation.id})
    response = client.get(detail_url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_organisation_retrieve_allowed_for_staff(staff_client, organisation):
    """Staff can retrieve organisation details."""
    detail_url = reverse("organisation-detail", kwargs={"pk": organisation.id})
    response = staff_client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_organisation_create_forbidden_for_agent(user_model):
    """Agents cannot create organisations through the API endpoint."""
    user = user_model.objects.create_user(
        email="maker@test.com",
        password="pass1234",
        first_name="Maker",
        last_name="User",
        account_type=user_model.AccountType.AGENT,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse("organisation-list")
    payload = {
        "name": "API Org",
        "industry": "Media",
        "address_country": "FR",
    }
    response = client.post(list_url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Organisation.objects.filter(name=payload["name"]).exists()


@pytest.mark.django_db
def test_organisation_create_forbidden_for_existing_collaborator(owner_client):
    """Collaborators already in an organisation cannot create another one."""
    list_url = reverse("organisation-list")
    payload = {"name": "Second Org", "industry": "Media", "address_country": "FR"}
    response = owner_client.post(list_url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_organisation_create_view_collaborator_success(user_model):
    """Collaborator accounts can create organisations and become owners."""
    user = user_model.objects.create_user(
        email="collab-maker@test.com",
        password="pass1234",
        first_name="CollabMaker",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse("organisation-list")
    payload = {
        "name": "Collaborator Org",
        "industry": "Media",
        "address_country": "FR",
    }
    response = client.post(list_url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    organisation = Organisation.objects.get(name=payload["name"])
    assert organisation.owner.user == user
    user.refresh_from_db()
    assert user.account_type == user_model.AccountType.COLLABORATOR
    assert Collaborator.objects.filter(
        user=user,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
    ).exists()


@pytest.mark.django_db
def test_organisation_update_as_owner(owner_client, organisation):
    """Owners may update organisation fields through the API."""
    detail_url = reverse("organisation-detail", kwargs={"pk": organisation.id})
    response = owner_client.patch(detail_url, {"description": "Updated"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    organisation.refresh_from_db()
    assert organisation.description == "Updated"


@pytest.mark.django_db
def test_organisation_update_forbidden_for_member(
    collaborator_client, member_collaborator
):
    """Members cannot modify organisation details."""
    organisation = member_collaborator.organisation
    detail_url = reverse("organisation-detail", kwargs={"pk": organisation.id})
    response = collaborator_client.patch(
        detail_url, {"description": "Should fail"}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_collaborator_list_action(owner_client, organisation):
    """Owners can list organisation collaborators."""
    url = reverse("organisation-collaborators", kwargs={"pk": organisation.id})
    response = owner_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) >= 1
    assert response.data[0]["user_email"] is not None


@pytest.mark.django_db
def test_add_collaborator_success(owner_client, organisation, user_model):
    """Owners can invite existing users as collaborators."""
    invitee = user_model.objects.create_user(
        email="invite2@test.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    url = reverse("organisation-add-collaborator", kwargs={"pk": organisation.id})
    response = owner_client.post(
        url,
        {
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Collaborator.objects.filter(user=invitee, organisation=organisation).exists()


@pytest.mark.django_db
def test_add_collaborator_rejects_agent(owner_client, organisation, user_model):
    """Inviting an agent account as collaborator returns a validation error."""
    invitee = user_model.objects.create_user(
        email="agent-collab@test.com",
        password="pass1234",
        account_type=user_model.AccountType.AGENT,
    )
    url = reverse("organisation-add-collaborator", kwargs={"pk": organisation.id})
    response = owner_client.post(
        url,
        {
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data


@pytest.mark.django_db
def test_add_collaborator_denied_without_feature(
    owner_client, organisation, user_model
):
    """Owners must have the collaborator invite feature to add teammates."""
    subscription = organisation.subscriptions.first()
    plan = subscription.plan
    plan.features["collaborator_invites"] = False
    plan.save(update_fields=["features"])

    invitee = user_model.objects.create_user(
        email="invite-feature@test.com", password="pass1234"
    )
    url = reverse("organisation-add-collaborator", kwargs={"pk": organisation.id})
    response = owner_client.post(
        url,
        {
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload["required_feature"] == "collaborator_invites"


@pytest.mark.django_db
def test_add_collaborator_forbidden_for_member(
    collaborator_client, member_collaborator
):
    """Members are blocked from inviting new collaborators."""
    organisation = member_collaborator.organisation
    url = reverse("organisation-add-collaborator", kwargs={"pk": organisation.id})
    response = collaborator_client.post(
        url,
        {
            "email": "newuser@test.com",
            "role": Collaborator.Role.MEMBER,
            "job_title": "Support",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_remove_collaborator_success(owner_client, organisation, user_model):
    """Owners can remove collaborators from the organisation."""
    target = user_model.objects.create_user(
        email="remove@test.com", password="pass1234"
    )
    collaborator = Collaborator.objects.create(
        user=target,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Temp",
    )
    url = reverse(
        "organisation-remove-collaborator", kwargs={"collaborator_id": collaborator.id}
    )
    response = owner_client.delete(url)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Collaborator.objects.filter(id=collaborator.id).exists()


@pytest.mark.django_db
def test_remove_collaborator_forbidden(
    collaborator_client, member_collaborator, user_model
):
    """Members are not allowed to remove other collaborators."""
    organisation = member_collaborator.organisation
    target = user_model.objects.create_user(email="stay@test.com", password="pass1234")
    collaborator = Collaborator.objects.create(
        user=target,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title="Support",
    )
    url = reverse(
        "organisation-remove-collaborator", kwargs={"collaborator_id": collaborator.id}
    )
    response = collaborator_client.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Collaborator.objects.filter(id=collaborator.id).exists()


@pytest.mark.django_db
def test_remove_collaborator_not_found(owner_client):
    """Deleting a non-existent collaborator returns a 404."""
    url = reverse(
        "organisation-remove-collaborator", kwargs={"collaborator_id": uuid.uuid4()}
    )
    response = owner_client.delete(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["detail"] == "Collaborator not found."


@pytest.mark.django_db
def test_add_collaborator_respects_plan_limit(
    owner_client, organisations_setup, user_model
):
    organisation = organisations_setup["organisation"]
    subscription = organisations_setup["subscription"]
    plan = subscription.plan
    plan.features["max_collaborators"] = 1
    plan.save(update_fields=["features"])

    invitee = user_model.objects.create_user(
        email="limit@test.com", password="pass1234"
    )
    url = reverse("organisation-add-collaborator", kwargs={"pk": organisation.id})
    response = owner_client.post(
        url,
        {
            "email": invitee.email,
            "role": Collaborator.Role.MEMBER,
            "job_title": "Analyst",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "max_collaborators"


@pytest.mark.django_db
def test_invite_creation_and_listing(owner_client, organisations_setup):
    organisation = organisations_setup["organisation"]
    url = reverse("organisation-invites", kwargs={"pk": organisation.id})

    create_response = owner_client.post(url, {"expires_in_hours": 24}, format="json")
    assert create_response.status_code == status.HTTP_201_CREATED
    assert OrganisationInvite.objects.filter(organisation=organisation).count() == 1

    list_response = owner_client.get(url)
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data) == 1


@pytest.mark.django_db
def test_join_organisation_via_invite(
    api_client, organisations_setup, collaborator_user
):
    organisation = organisations_setup["organisation"]
    owner = organisations_setup["owner"]
    owner_client = APIClient()
    owner_client.force_authenticate(user=owner)
    invite_url = reverse("organisation-invites", kwargs={"pk": organisation.id})
    invite_response = owner_client.post(
        invite_url, {"expires_in_hours": 1}, format="json"
    )
    assert invite_response.status_code == status.HTTP_201_CREATED
    code = invite_response.data["code"]

    api_client.force_authenticate(user=collaborator_user)
    join_url = reverse("organisation-join")
    response = api_client.post(
        join_url,
        {"code": code, "job_title": "Marketing Lead"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    collaborator = Collaborator.objects.get(user=collaborator_user)
    assert collaborator.organisation == organisation
    assert collaborator.job_title == "Marketing Lead"
    assert OrganisationInvite.objects.get(code=code).is_used is True


@pytest.mark.django_db
def test_update_job_title_as_owner(owner_client, organisation, member_collaborator):
    url = reverse(
        "organisation-update-job-title",
        kwargs={"pk": organisation.id, "collaborator_id": member_collaborator.id},
    )
    response = owner_client.patch(url, {"job_title": "Updated Role"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    member_collaborator.refresh_from_db()
    assert member_collaborator.job_title == "Updated Role"


@pytest.mark.django_db
def test_update_job_title_as_member(collaborator_client, member_collaborator):
    organisation = member_collaborator.organisation
    url = reverse(
        "organisation-update-job-title",
        kwargs={"pk": organisation.id, "collaborator_id": member_collaborator.id},
    )
    response = collaborator_client.patch(
        url, {"job_title": "Self Updated"}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    member_collaborator.refresh_from_db()
    assert member_collaborator.job_title == "Self Updated"


@pytest.mark.django_db
def test_transfer_ownership(owner_client, organisation, member_collaborator):
    url = reverse("organisation-transfer-ownership", kwargs={"pk": organisation.id})
    response = owner_client.post(
        url,
        {"collaborator_id": str(member_collaborator.id)},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    organisation.refresh_from_db()
    member_collaborator.refresh_from_db()
    assert member_collaborator.role == Collaborator.Role.OWNER
    assert organisation.owner.user == member_collaborator.user


@pytest.mark.django_db
def test_remove_collaborator_requires_feature(
    monkeypatch, owner_client, organisation, member_collaborator
):
    url = reverse(
        "organisation-remove-collaborator",
        kwargs={"collaborator_id": member_collaborator.id},
    )
    monkeypatch.setattr(
        "organisations.views.collaborator_meets_requirement",
        lambda user, requirement: False,
    )
    response = owner_client.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "required_feature" in response.data


@pytest.mark.django_db
def test_invite_creation_without_owner_returns_400(
    user_model, organisations_setup, monkeypatch
):
    organisation = organisations_setup["organisation"]
    organisation.collaborators.all().delete()
    staff_user = user_model.objects.create_user(
        email="staff@example.com",
        password="pass1234",
        is_staff=True,
    )
    monkeypatch.setattr(
        "organisations.views.IsOrganisationOwner.has_permission",
        lambda self, request, view: True,
    )
    client = APIClient()
    client.force_authenticate(user=staff_user)
    url = reverse("organisation-invites", kwargs={"pk": organisation.id})
    response = client.post(url, {"expires_in_hours": 12}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_invite_serializer_generates_unique_code(monkeypatch, organisations_setup):
    organisation = organisations_setup["organisation"]
    owner_collaborator = organisation.collaborators.get(role=Collaborator.Role.OWNER)
    call_count = {"value": 0}

    def fake_code():
        call_count["value"] += 1
        return (
            "DUPLICATE" if call_count["value"] < 2 else f"UNIQUE{call_count['value']}"
        )

    monkeypatch.setattr(
        "organisations.models.OrganisationInvite.generate_code",
        staticmethod(fake_code),
    )
    OrganisationInvite.objects.create(
        organisation=organisation,
        created_by=owner_collaborator,
        code="DUPLICATE",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    serializer = OrganisationInviteCreateSerializer(
        data={},
        context={"organisation": organisation, "creator": owner_collaborator},
    )
    assert serializer.is_valid(), serializer.errors
    invite = serializer.save()
    assert invite.code.startswith("UNIQUE")


@pytest.mark.django_db
def test_organisation_slug_deduplicates(user_model):
    owner = user_model.objects.create_user(
        email="slug-owner@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    Organisation.objects.create(owner=owner, name="ACME!", type=Organisation.Type.BRAND)
    org2 = Organisation.objects.create(
        owner=owner, name="ACME?", type=Organisation.Type.BRAND
    )
    assert org2.slug.startswith("acme") and org2.slug != "acme"
