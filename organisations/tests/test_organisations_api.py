"""Tests for organisation models, serializers, permissions and API views."""

# pylint: skip-file

import uuid

import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.pagination import PageNumberPagination

from organisations.models import Collaborator, Organisation
from organisations.permissions import IsAuthenticatedCollaborator, IsOrganisationOwner
from organisations.serializers import (
    CollaboratorCreateSerializer,
    CollaboratorSerializer,
    OrganisationCreateSerializer,
    OrganisationListFilter,
    OrganisationSerializer,
)
from users.models import AgentProfile


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
def collaborator_user(user_model):
    """Create and return a collaborator account for membership tests."""
    user = user_model.objects.create_user(
        email='collab@test.com',
        password='pass1234',
        first_name='Collab',
        last_name='User',
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
    return organisations_setup['organisation']


@pytest.fixture
def member_collaborator(collaborator_user, organisation):
    """Return a collaborator with member role attached to the organisation."""
    return Collaborator.objects.create(
        user=collaborator_user,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title='Member',
    )


@pytest.mark.django_db
def test_organisation_str(organisation):
    """Organisation string representation returns its name."""
    assert str(organisation) == organisation.name


@pytest.mark.django_db
def test_organisation_get_owner_id(organisations_setup):
    """Return the owner collaborator identifier when present."""
    organisation = organisations_setup['organisation']
    collaborator = organisations_setup['collaborator']
    assert organisation.owner == collaborator.user
    assert organisation.get_owner_id() == collaborator.id
    collaborator.delete()
    assert organisation.get_owner_id() is None


@pytest.mark.django_db
def test_collaborator_str(organisations_setup):
    """Collaborator string displays user, organisation and role."""
    collaborator = organisations_setup['collaborator']
    expected = f"{collaborator.user} - {collaborator.organisation.name} ({collaborator.role})"
    assert str(collaborator) == expected


@pytest.mark.django_db
def test_organisation_serializer_owner_field(organisations_setup):
    """Organisation serializer exposes the owner collaborator id."""
    organisation = organisations_setup['organisation']
    data = OrganisationSerializer(organisation).data
    assert data['owner_id'] == str(organisations_setup['collaborator'].id)


@pytest.mark.django_db
def test_organisation_create_serializer(factory, user_model):
    """Creating an organisation promotes the creator to owner."""
    user = user_model.objects.create_user(
        email='creator@test.com',
        password='pass1234',
        first_name='Creator',
        last_name='User',
        account_type=user_model.AccountType.AGENT,
    )
    request = factory.post('/api/organisations/')
    request.user = user
    serializer = OrganisationCreateSerializer(
        data={
            'name': 'Created Org',
            'sector': 'Tech',
            'size': Organisation.Size.SMALL,
            'budget_min': 1000,
            'budget_max': 2000,
            'country': 'FR',
            'description': 'New organisation',
            'website': 'https://example.com',
        },
        context={'request': request},
    )
    assert serializer.is_valid(), serializer.errors
    organisation = serializer.save()
    user.refresh_from_db()
    assert user.account_type == user_model.AccountType.COLLABORATOR
    assert organisation.owner == user
    assert Collaborator.objects.filter(user=user, organisation=organisation, role=Collaborator.Role.OWNER).exists()


@pytest.mark.django_db
def test_collaborator_serializer_fields(organisations_setup):
    """Collaborator serializer exposes related user metadata."""
    collaborator = organisations_setup['collaborator']
    data = CollaboratorSerializer(collaborator).data
    assert data['user_email'] == collaborator.user.email
    assert data['user_full_name'] == str(collaborator.user)
    assert data['role'] == collaborator.role


@pytest.mark.django_db
def test_collaborator_create_serializer_validate_role(organisation):
    """Reject invitations that attempt to promote to owner via serializer."""
    serializer = CollaboratorCreateSerializer(
        data={'email': 'x@test.com', 'role': Collaborator.Role.OWNER, 'job_title': 'Owner'},
        context={'organisation': organisation},
    )
    assert not serializer.is_valid()
    assert 'role' in serializer.errors


@pytest.mark.django_db
def test_organisation_deleted_when_owner_removed(organisations_setup):
    """Organisation cascades when the owner user is deleted."""
    organisation = organisations_setup['organisation']
    owner = organisation.owner
    owner.delete()
    assert not Organisation.objects.filter(id=organisation.id).exists()


@pytest.mark.django_db
def test_collaborator_create_serializer_validate_duplicate(organisations_setup):
    """Ensure duplicate collaborator invitations are rejected."""
    organisation = organisations_setup['organisation']
    existing_email = organisations_setup['collaborator'].user.email
    serializer = CollaboratorCreateSerializer(
        data={'email': existing_email, 'role': Collaborator.Role.MEMBER, 'job_title': 'Analyst'},
        context={'organisation': organisation},
    )
    assert not serializer.is_valid()
    assert 'email' in serializer.errors


@pytest.mark.django_db
def test_collaborator_create_serializer_missing_user(organisation):
    """Raise a validation error when the invitee does not exist."""
    serializer = CollaboratorCreateSerializer(
        data={'email': 'missing@test.com', 'role': Collaborator.Role.MEMBER, 'job_title': 'Analyst'},
        context={'organisation': organisation},
    )
    assert serializer.is_valid()
    with pytest.raises(serializers.ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_collaborator_create_serializer_success(organisation, user_model):
    """Successfully add an existing user as a collaborator."""
    invitee = user_model.objects.create_user(email='invitee@test.com', password='pass1234')
    serializer = CollaboratorCreateSerializer(
        data={'email': invitee.email, 'role': Collaborator.Role.MEMBER, 'job_title': 'Analyst'},
        context={'organisation': organisation},
    )
    assert serializer.is_valid(), serializer.errors
    collaborator = serializer.save()
    assert collaborator.user == invitee
    assert collaborator.organisation == organisation


@pytest.mark.django_db
def test_organisation_list_filter_validation():
    """Organisation list filter accepts optional query parameters."""
    serializer = OrganisationListFilter(data={'sector': 'Tech', 'size': Organisation.Size.MEDIUM, 'country': 'FR'})
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_is_authenticated_collaborator_permission(factory, owner_user, organisation, user_model):
    """Permission grants access only to authenticated collaborators."""
    permission = IsAuthenticatedCollaborator()
    request = factory.get('/')
    request.user = owner_user

    class Dummy:
        pass

    view_without_org = Dummy()
    assert not permission.has_permission(request, view_without_org)

    outsider = user_model.objects.create_user(email='outsider@test.com', password='pass1234')
    view = Dummy()
    view.organisation = organisation
    request.user = outsider
    assert not permission.has_permission(request, view)

    request.user = owner_user
    assert permission.has_permission(request, view)


@pytest.mark.django_db
def test_is_organisation_owner_permission(factory, owner_user, organisation, member_collaborator):
    """Permission ensures only owners may perform privileged actions."""
    permission = IsOrganisationOwner()

    class Dummy:
        pass

    view = Dummy()
    view.organisation = organisation
    view_without_org = Dummy()

    request = factory.get('/')
    request.user = member_collaborator.user
    assert not permission.has_permission(request, view)

    request.user = owner_user
    assert permission.has_permission(request, view)

    request.user = owner_user
    assert not permission.has_permission(request, view_without_org)


@pytest.mark.django_db
def test_organisation_list_and_filter(owner_client, organisation):
    """List endpoint supports filtering by organisation attributes."""
    list_url = reverse('organisation-list')
    response = owner_client.get(list_url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) >= 1

    Organisation.objects.create(
        owner=organisation.owner,
        name='Filtered Org',
        sector='Sportswear',
        size=Organisation.Size.SMALL,
        budget_min=500,
        budget_max=800,
        country='FR',
    )
    filtered = owner_client.get(list_url, {'sector': 'Sportswear'})
    assert filtered.status_code == status.HTTP_200_OK
    assert len(filtered.data) == 1
    assert filtered.data[0]['name'] == 'Filtered Org'


@pytest.mark.django_db
def test_organisation_list_forbidden_for_agent(agent_user):
    """Agents are not allowed to list organisations."""
    client = APIClient()
    client.force_authenticate(user=agent_user)
    list_url = reverse('organisation-list')
    response = client.get(list_url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_organisation_list_pagination(owner_client, organisation):
    """List endpoint applies pagination when configured on the viewset."""
    class SingleItemPagination(PageNumberPagination):
        page_size = 1

    Organisation.objects.create(
        owner=organisation.owner,
        name='Second Org',
        sector='Tech',
        size=Organisation.Size.SMALL,
        budget_min=500,
        budget_max=900,
        country='FR',
    )

    list_url = reverse('organisation-list')
    with patch('organisations.views.OrganisationViewSet.pagination_class', SingleItemPagination):
        response = owner_client.get(list_url)

    assert response.status_code == status.HTTP_200_OK
    assert 'results' in response.data
    assert len(response.data['results']) == 1


@pytest.mark.django_db
def test_organisation_retrieve(owner_client, organisation):
    """Retrieve endpoint returns organisation details for owners."""
    detail_url = reverse('organisation-detail', kwargs={'pk': organisation.id})
    response = owner_client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['name'] == organisation.name


@pytest.mark.django_db
def test_organisation_create_forbidden_for_agent(user_model):
    """Agents cannot create organisations through the API endpoint."""
    user = user_model.objects.create_user(
        email='maker@test.com',
        password='pass1234',
        first_name='Maker',
        last_name='User',
        account_type=user_model.AccountType.AGENT,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse('organisation-list')
    payload = {
        'name': 'API Org',
        'sector': 'Media',
        'size': Organisation.Size.MEDIUM,
        'budget_min': 300,
        'budget_max': 900,
        'country': 'FR',
    }
    response = client.post(list_url, payload, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Organisation.objects.filter(name=payload['name']).exists()


@pytest.mark.django_db
def test_organisation_create_view_collaborator_success(user_model):
    """Collaborator accounts can create organisations and become owners."""
    user = user_model.objects.create_user(
        email='collab-maker@test.com',
        password='pass1234',
        first_name='CollabMaker',
        last_name='User',
        account_type=user_model.AccountType.COLLABORATOR,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse('organisation-list')
    payload = {
        'name': 'Collaborator Org',
        'sector': 'Media',
        'size': Organisation.Size.MEDIUM,
        'budget_min': 300,
        'budget_max': 900,
        'country': 'FR',
    }
    response = client.post(list_url, payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    organisation = Organisation.objects.get(name=payload['name'])
    assert organisation.owner == user
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
    detail_url = reverse('organisation-detail', kwargs={'pk': organisation.id})
    response = owner_client.patch(detail_url, {'description': 'Updated'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    organisation.refresh_from_db()
    assert organisation.description == 'Updated'


@pytest.mark.django_db
def test_organisation_update_forbidden_for_member(collaborator_client, member_collaborator):
    """Members cannot modify organisation details."""
    organisation = member_collaborator.organisation
    detail_url = reverse('organisation-detail', kwargs={'pk': organisation.id})
    response = collaborator_client.patch(detail_url, {'description': 'Should fail'}, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_collaborator_list_action(owner_client, organisation):
    """Owners can list organisation collaborators."""
    url = reverse('organisation-collaborators', kwargs={'pk': organisation.id})
    response = owner_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) >= 1
    assert response.data[0]['user_email'] is not None


@pytest.mark.django_db
def test_add_collaborator_success(owner_client, organisation, user_model):
    """Owners can invite existing users as collaborators."""
    invitee = user_model.objects.create_user(email='invite2@test.com', password='pass1234')
    url = reverse('organisation-add-collaborator', kwargs={'pk': organisation.id})
    response = owner_client.post(url, {
        'email': invitee.email,
        'role': Collaborator.Role.MEMBER,
        'job_title': 'Analyst',
    }, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert Collaborator.objects.filter(user=invitee, organisation=organisation).exists()


@pytest.mark.django_db
def test_add_collaborator_denied_without_feature(owner_client, organisation, user_model):
    """Owners must have the collaborator invite feature to add teammates."""
    subscription = organisation.subscriptions.first()
    plan = subscription.plan
    plan.features['collaborator_invites'] = False
    plan.save(update_fields=['features'])

    invitee = user_model.objects.create_user(email='invite-feature@test.com', password='pass1234')
    url = reverse('organisation-add-collaborator', kwargs={'pk': organisation.id})
    response = owner_client.post(url, {
        'email': invitee.email,
        'role': Collaborator.Role.MEMBER,
        'job_title': 'Analyst',
    }, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    payload = response.json()
    assert payload['required_feature'] == 'collaborator_invites'


@pytest.mark.django_db
def test_add_collaborator_forbidden_for_member(collaborator_client, member_collaborator):
    """Members are blocked from inviting new collaborators."""
    organisation = member_collaborator.organisation
    url = reverse('organisation-add-collaborator', kwargs={'pk': organisation.id})
    response = collaborator_client.post(url, {
        'email': 'newuser@test.com',
        'role': Collaborator.Role.MEMBER,
        'job_title': 'Support',
    }, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_remove_collaborator_success(owner_client, organisation, user_model):
    """Owners can remove collaborators from the organisation."""
    target = user_model.objects.create_user(email='remove@test.com', password='pass1234')
    collaborator = Collaborator.objects.create(
        user=target,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title='Temp',
    )
    url = reverse('organisation-remove-collaborator', kwargs={'collaborator_id': collaborator.id})
    response = owner_client.delete(url)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Collaborator.objects.filter(id=collaborator.id).exists()


@pytest.mark.django_db
def test_remove_collaborator_forbidden(collaborator_client, member_collaborator, user_model):
    """Members are not allowed to remove other collaborators."""
    organisation = member_collaborator.organisation
    target = user_model.objects.create_user(email='stay@test.com', password='pass1234')
    collaborator = Collaborator.objects.create(
        user=target,
        organisation=organisation,
        role=Collaborator.Role.MEMBER,
        job_title='Support',
    )
    url = reverse('organisation-remove-collaborator', kwargs={'collaborator_id': collaborator.id})
    response = collaborator_client.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Collaborator.objects.filter(id=collaborator.id).exists()


@pytest.mark.django_db
def test_remove_collaborator_not_found(owner_client):
    """Deleting a non-existent collaborator returns a 404."""
    url = reverse('organisation-remove-collaborator', kwargs={'collaborator_id': uuid.uuid4()})
    response = owner_client.delete(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data['detail'] == 'Collaborator not found.'


@pytest.mark.django_db
def test_add_collaborator_respects_plan_limit(owner_client, organisations_setup, user_model):
    organisation = organisations_setup['organisation']
    subscription = organisations_setup['subscription']
    plan = subscription.plan
    plan.features['max_collaborators'] = 1
    plan.save(update_fields=['features'])

    invitee = user_model.objects.create_user(email='limit@test.com', password='pass1234')
    url = reverse('organisation-add-collaborator', kwargs={'pk': organisation.id})
    response = owner_client.post(url, {
        'email': invitee.email,
        'role': Collaborator.Role.MEMBER,
        'job_title': 'Analyst',
    }, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['required_feature'] == 'max_collaborators'
