"""Integration tests for the athletes API endpoints."""


from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework import permissions, status
from rest_framework.test import APIClient, APIRequestFactory

from athletes.models import Athlete, Sport
from athletes.permissions import IsAgentUser, IsAthleteOwner
from athletes.serializers import AthletePublicSerializer, AthleteSerializer, SportSerializer
from athletes.views import AthleteViewSet
from payments.models import Subscription, SubscriptionPlan
from users.models import AgentProfile


@pytest.fixture
def sport():
    return Sport.objects.create(name='Basketball', discipline='Team Sport')


@pytest.fixture
def agent_profile(agent_user):
    return agent_user.agent_profile


@pytest.fixture
def other_agent_user(user_model):
    user = user_model.objects.create_user(
        email='otheragent@example.com',
        password='pass1234',
        first_name='Other',
        last_name='Agent',
    )
    AgentProfile.objects.create(user=user, display_name='Other Agent')
    return user


@pytest.fixture
def athlete(agent_profile, sport):
    return Athlete.objects.create(
        sport=sport,
        agent=agent_profile,
        full_name='John Doe',
        birth_date=date(1990, 1, 1),
        nationality='FR',
        bio='Original bio',
        social_links={'instagram': 'john_doe'},
    )


@pytest.mark.django_db
def test_sport_str(sport):
    assert str(sport) == sport.name


@pytest.mark.django_db
def test_athlete_str(athlete):
    assert str(athlete) == athlete.full_name


@pytest.mark.django_db
def test_is_agent_user_permission(agent_user, user_model):
    permission = IsAgentUser()
    factory = APIRequestFactory()

    request = factory.get('/')
    request.user = AnonymousUser()
    assert not permission.has_permission(request, None)

    request.user = agent_user
    assert permission.has_permission(request, None)

    user_without_profile = user_model.objects.create_user(
        email='noprof@example.com',
        password='pass1234',
    )
    request.user = user_without_profile
    assert not permission.has_permission(request, None)


@pytest.mark.django_db
def test_is_athlete_owner_permission(agent_user, other_agent_user, athlete, user_model):
    permission = IsAthleteOwner()
    factory = APIRequestFactory()

    request = factory.patch('/')
    request.user = AnonymousUser()
    assert not permission.has_object_permission(request, None, athlete)

    request.user = agent_user
    assert permission.has_object_permission(request, None, athlete)

    request.user = other_agent_user
    assert not permission.has_object_permission(request, None, athlete)

    no_profile_user = user_model.objects.create_user(
        email='noperm@example.com',
        password='pass1234',
    )
    request.user = no_profile_user
    assert not permission.has_object_permission(request, None, athlete)


@pytest.mark.django_db
def test_athlete_serializer_create_success(agent_user, sport):
    factory = APIRequestFactory()
    request = factory.post('/api/athletes/')
    request.user = agent_user
    serializer = AthleteSerializer(
        data={
            'sport_id': sport.id,
            'full_name': 'Jane Doe',
            'birth_date': '1995-05-05',
            'nationality': 'US',
            'bio': 'Bio text',
            'social_links': {'twitter': 'jane_doe'},
            'is_self_represented': False,
        },
        context={'request': request},
    )
    assert serializer.is_valid(), serializer.errors
    athlete = serializer.save()
    assert athlete.agent == agent_user.agent_profile
    assert athlete.sport == sport
    assert athlete.full_name == 'Jane Doe'


@pytest.mark.django_db
def test_athlete_serializer_requires_agent_profile(user_model, sport):
    user = user_model.objects.create_user(
        email='noagent@example.com',
        password='pass1234',
    )
    factory = APIRequestFactory()
    request = factory.post('/api/athletes/')
    request.user = user
    serializer = AthleteSerializer(
        data={
            'sport_id': sport.id,
            'full_name': 'No Agent',
            'birth_date': '1990-01-01',
            'nationality': 'FR',
        },
        context={'request': request},
    )
    assert not serializer.is_valid()
    assert 'non_field_errors' in serializer.errors


@pytest.mark.django_db
def test_athlete_serializer_update_blocks_other_agent(athlete, other_agent_user):
    factory = APIRequestFactory()
    request = factory.patch('/api/athletes/')
    request.user = other_agent_user
    serializer = AthleteSerializer(
        athlete,
        data={'bio': 'Should fail'},
        context={'request': request},
        partial=True,
    )
    assert not serializer.is_valid()
    assert 'agent' in serializer.errors


@pytest.mark.django_db
def test_athlete_serializer_update_success(athlete, agent_user):
    factory = APIRequestFactory()
    request = factory.patch('/api/athletes/')
    request.user = agent_user
    serializer = AthleteSerializer(
        athlete,
        data={'bio': 'Updated bio'},
        context={'request': request},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.bio == 'Updated bio'


@pytest.mark.django_db
def test_athlete_public_serializer(athlete):
    data = AthletePublicSerializer(athlete).data
    assert data['full_name'] == athlete.full_name
    assert 'bio' not in data


@pytest.mark.django_db
def test_sport_serializer(sport):
    data = SportSerializer(sport).data
    assert data['name'] == sport.name
    assert data['discipline'] == sport.discipline


@pytest.mark.django_db
def test_athlete_list_requires_authentication(athlete):
    client = APIClient()
    url = reverse('athlete-list')
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_list_forbidden_for_agents(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-list')
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_list_allows_collaborator_with_subscription(
    athlete,
    owner_user,
    organisation_subscription,
):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse('athlete-list')
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]['full_name'] == athlete.full_name
    assert 'bio' in response.data[0]


@pytest.mark.django_db
def test_athlete_retrieve_requires_authentication(athlete):
    client = APIClient()
    url = reverse('athlete-detail', kwargs={'pk': athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_retrieve_authenticated_success(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-detail', kwargs={'pk': athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['full_name'] == athlete.full_name


@pytest.mark.django_db
def test_athlete_retrieve_allows_collaborator(athlete, owner_user, organisation_subscription):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse('athlete-detail', kwargs={'pk': athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['full_name'] == athlete.full_name


@pytest.mark.django_db
def test_athlete_create_requires_agent_user(user_model, sport):
    client = APIClient()
    user = user_model.objects.create_user(
        email='organisation@example.com',
        password='pass1234',
        account_type=user_model.AccountType.COLLABORATOR,
    )
    client.force_authenticate(user=user)
    url = reverse('athlete-list')
    response = client.post(url, {
        'sport_id': sport.id,
        'full_name': 'Blocked User',
        'birth_date': '1999-09-09',
        'nationality': 'FR',
    }, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_create_success(agent_user, sport):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-list')
    response = client.post(url, {
        'sport_id': sport.id,
        'full_name': 'Created Athlete',
        'birth_date': '2001-01-01',
        'nationality': 'US',
        'bio': 'New bio',
    }, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert Athlete.objects.filter(full_name='Created Athlete').exists()


@pytest.mark.django_db
def test_athlete_update_requires_owner(athlete, other_agent_user, sport):
    client = APIClient()
    client.force_authenticate(user=other_agent_user)
    url = reverse('athlete-detail', kwargs={'pk': athlete.id})
    response = client.patch(url, {'bio': 'Attempted update'}, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_update_success(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-detail', kwargs={'pk': athlete.id})
    response = client.patch(url, {'bio': 'Updated via API'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    athlete.refresh_from_db()
    assert athlete.bio == 'Updated via API'


@pytest.mark.django_db
def test_sport_list_view_orders_by_name():
    Sport.objects.create(name='Z Sport', discipline='Z Disc')
    Sport.objects.create(name='A Sport', discipline='A Disc')
    client = APIClient()
    response = client.get(reverse('sports-list'))
    assert response.status_code == status.HTTP_200_OK
    names = [item['name'] for item in response.data]
    assert names == sorted(names)


@pytest.mark.django_db
def test_athlete_viewset_default_permissions(agent_user):
    view = AthleteViewSet()
    view.action = 'destroy'
    request = APIRequestFactory().delete('/')
    request.user = agent_user
    view.request = request
    permissions_list = view.get_permissions()
    assert len(permissions_list) == 2
    assert all(isinstance(item, permissions.BasePermission) for item in permissions_list)


@pytest.mark.django_db
def test_agent_create_athlete_limit_enforced(agent_user, sport):
    plan = SubscriptionPlan.objects.create(
        code='agent-free-test',
        name='Agent Free Test',
        price='0.00',
        features={'max_athletes': 1},
    )
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=date(2025, 1, 1),
        current_period_end=date(2025, 12, 31),
    )

    Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name='Initial Athlete',
        birth_date=date(1990, 1, 1),
        nationality='FR',
    )
    assert Athlete.objects.filter(agent=agent_user.agent_profile).count() == 1

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-list')
    payload = {
        'sport_id': sport.id,
        'full_name': 'Second Athlete',
        'birth_date': '1992-02-02',
        'nationality': 'US',
    }
    response = client.post(url, payload, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['required_feature'] == 'max_athletes'


@pytest.mark.django_db
def test_agent_create_athlete_requires_plan_slot(agent_user, sport):
    plan = SubscriptionPlan.objects.create(
        code='agent-zero-slot',
        name='Agent Zero Slot',
        price='0.00',
        features={'max_athletes': 0},
    )
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=date(2025, 1, 1),
        current_period_end=date(2025, 12, 31),
    )

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse('athlete-list')
    payload = {
        'sport_id': sport.id,
        'full_name': 'Blocked Athlete',
        'birth_date': '1993-03-03',
        'nationality': 'US',
    }
    response = client.post(url, payload, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['required_feature'] == 'max_athletes'
