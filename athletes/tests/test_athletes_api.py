"""Integration tests for the athletes API endpoints."""

from datetime import date, datetime, time

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.test import APIClient, APIRequestFactory

from athletes.models import Athlete, AthletePhoto, Sport, SportDiscipline
from athletes.permissions import IsAgentUser, IsAthleteOwner
from athletes.serializers import (
    AthletePublicSerializer,
    AthleteSerializer,
    SportSerializer,
)
from athletes.views import AthleteViewSet
from payments.models import Subscription, SubscriptionPlan
from users.models import AgentProfile


SMALL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc``\x00"
    b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def sample_image_file(name: str) -> SimpleUploadedFile:
    """Return a minimal in-memory PNG for image uploads in tests."""

    return SimpleUploadedFile(name, SMALL_PNG, content_type="image/png")


def aware_datetime(value: date) -> datetime:
    """Return a timezone-aware midnight datetime for the given date."""

    return timezone.make_aware(datetime.combine(value, time.min))


@pytest.fixture
def sport():
    sport = Sport.objects.create(
        name="Basketball",
        emoji="🏀",
        category=Sport.Category.TEAM,
    )
    SportDiscipline.objects.create(
        sport=sport,
        name="Professional 5v5",
        description="Standard full-court play",
        is_olympic=True,
    )
    SportDiscipline.objects.create(
        sport=sport,
        name="Streetball",
        description="3x3 outdoor variant",
        is_olympic=False,
    )
    return sport


@pytest.fixture
def agent_profile(agent_user):
    return agent_user.agent_profile


@pytest.fixture
def other_agent_user(user_model):
    user = user_model.objects.create_user(
        email="otheragent@example.com",
        password="pass1234",
        first_name="Other",
        last_name="Agent",
    )
    AgentProfile.objects.create(user=user)
    return user


@pytest.fixture
def athlete(agent_profile, sport):
    return Athlete.objects.create(
        sport=sport,
        agent=agent_profile,
        full_name="John Doe",
        birth_date=date(1990, 1, 1),
        nationality="FR",
        bio="Original bio",
        social_links={"instagram": "john_doe"},
    )


@pytest.mark.django_db
def test_sport_str(sport):
    assert str(sport) == sport.name


@pytest.mark.django_db
def test_athlete_str(athlete):
    assert str(athlete) == athlete.full_name


@pytest.mark.django_db
def test_retrieve_athlete_by_slug(api_client, athlete):
    url = reverse("athlete-by-slug", kwargs={"slug": athlete.slug})
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(athlete.id)
    assert response.data["slug"] == athlete.slug
    assert response.data["full_name"] == athlete.full_name


@pytest.mark.django_db
def test_is_agent_user_permission(agent_user, user_model):
    permission = IsAgentUser()
    factory = APIRequestFactory()

    request = factory.get("/")
    request.user = AnonymousUser()
    assert not permission.has_permission(request, None)

    request.user = agent_user
    assert permission.has_permission(request, None)

    user_without_profile = user_model.objects.create_user(
        email="noprof@example.com",
        password="pass1234",
    )
    request.user = user_without_profile
    assert not permission.has_permission(request, None)


@pytest.mark.django_db
def test_is_athlete_owner_permission(agent_user, other_agent_user, athlete, user_model):
    permission = IsAthleteOwner()
    factory = APIRequestFactory()

    request = factory.patch("/")
    request.user = AnonymousUser()
    assert not permission.has_object_permission(request, None, athlete)

    request.user = agent_user
    assert permission.has_object_permission(request, None, athlete)

    request.user = other_agent_user
    assert not permission.has_object_permission(request, None, athlete)

    no_profile_user = user_model.objects.create_user(
        email="noperm@example.com",
        password="pass1234",
    )
    request.user = no_profile_user
    assert not permission.has_object_permission(request, None, athlete)


@pytest.mark.django_db
def test_athlete_serializer_create_success(agent_user, sport):
    factory = APIRequestFactory()
    request = factory.post("/api/athletes/")
    request.user = agent_user
    serializer = AthleteSerializer(
        data={
            "sport_id": sport.id,
            "full_name": "Jane Doe",
            "birth_date": "1995-05-05",
            "nationality": "US",
            "country": "US",
            "city": "New York",
            "bio": "Bio text",
            "social_links": {"twitter": "jane_doe"},
            "discipline_ids": [str(d.id) for d in sport.disciplines.all()],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    athlete = serializer.save()
    assert athlete.agent == agent_user.agent_profile
    assert athlete.sport == sport
    assert athlete.full_name == "Jane Doe"
    assert athlete.country == "US"
    assert athlete.city == "New York"
    assert list(
        athlete.disciplines.order_by("name").values_list("name", flat=True)
    ) == ["Professional 5v5", "Streetball"]


@pytest.mark.django_db
def test_athlete_serializer_adds_gallery_photos(agent_user, sport):
    factory = APIRequestFactory()
    request = factory.post("/api/athletes/")
    request.user = agent_user
    serializer = AthleteSerializer(
        data={
            "sport_id": sport.id,
            "full_name": "Media Athlete",
            "birth_date": "1992-03-03",
            "nationality": "FR",
            "country": "FR",
            "city": "Paris",
            "new_photos": [
                sample_image_file("gallery1.png"),
                sample_image_file("gallery2.png"),
            ],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    athlete = serializer.save()
    athlete.refresh_from_db()
    assert athlete.photos.count() == 2
    positions = list(
        athlete.photos.order_by("position").values_list("position", flat=True)
    )
    assert positions == [1, 2]


@pytest.mark.django_db
def test_athlete_serializer_requires_agent_profile(user_model, sport):
    user = user_model.objects.create_user(
        email="noagent@example.com",
        password="pass1234",
    )
    factory = APIRequestFactory()
    request = factory.post("/api/athletes/")
    request.user = user
    serializer = AthleteSerializer(
        data={
            "sport_id": sport.id,
            "full_name": "No Agent",
            "birth_date": "1990-01-01",
            "nationality": "FR",
        },
        context={"request": request},
    )
    assert not serializer.is_valid()
    assert "non_field_errors" in serializer.errors


@pytest.mark.django_db
def test_athlete_serializer_update_blocks_other_agent(athlete, other_agent_user):
    factory = APIRequestFactory()
    request = factory.patch("/api/athletes/")
    request.user = other_agent_user
    serializer = AthleteSerializer(
        athlete,
        data={"bio": "Should fail"},
        context={"request": request},
        partial=True,
    )
    assert not serializer.is_valid()
    assert "agent" in serializer.errors


@pytest.mark.django_db
def test_athlete_serializer_update_success(athlete, agent_user):
    factory = APIRequestFactory()
    request = factory.patch("/api/athletes/")
    request.user = agent_user
    serializer = AthleteSerializer(
        athlete,
        data={"bio": "Updated bio"},
        context={"request": request},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.bio == "Updated bio"


@pytest.mark.django_db
def test_athlete_public_serializer(athlete):
    data = AthletePublicSerializer(athlete).data
    assert data["full_name"] == athlete.full_name
    assert data["country"] == ""
    assert data["city"] == ""
    assert "bio" not in data
    assert data["disciplines"] == []
    assert data["card_photos"] == []
    assert data["gallery_photos"] == []
    assert "agent" in data
    assert data["agent"]["id"] == str(athlete.agent.id)
    assert data["agent"]["name"] == str(athlete.agent.user)
    assert data["agent"]["email"] == athlete.agent.user.email


@pytest.mark.django_db
def test_athlete_public_serializer_card_photos(athlete):
    athlete.country = "FR"
    athlete.city = "Paris"
    athlete.save(update_fields=["country", "city", "updated_at"])
    for index in range(4):
        AthletePhoto.objects.create(
            athlete=athlete,
            image=sample_image_file(f"carousel{index}.png"),
            position=index,
        )
    data = AthletePublicSerializer(athlete).data
    assert data["country"] == "FR"
    assert data["city"] == "Paris"
    assert len(data["card_photos"]) == 3
    assert all(photo_path.endswith(".png") for photo_path in data["card_photos"])
    assert len(data["gallery_photos"]) == 4


@pytest.mark.django_db
def test_athlete_photos_endpoint(api_client, athlete):
    for index in range(2):
        AthletePhoto.objects.create(
            athlete=athlete,
            image=sample_image_file(f"gallery{index}.png"),
            position=index,
        )
    url = reverse("athlete-photos", kwargs={"athlete_id": athlete.id})
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["athlete_id"] == str(athlete.id)
    assert len(payload["photos"]) == 2
    assert all(item["image"].endswith(".png") for item in payload["photos"])


@pytest.mark.django_db
def test_sport_serializer(sport):
    data = SportSerializer(sport).data
    assert data["name"] == sport.name
    assert data["slug"] == sport.slug
    assert data["disciplines"][0]["name"] == "Professional 5v5"


@pytest.mark.django_db
def test_sport_disciplines_endpoint(api_client, sport):
    url = reverse("sport-disciplines", kwargs={"sport_id": sport.id})
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["sport"]["id"] == str(sport.id)
    names = [item["name"] for item in payload["disciplines"]]
    assert names == sorted(names)


@pytest.mark.django_db
def test_my_athletes_view_returns_only_owned_athletes(
    api_client, agent_user, athlete, sport, other_agent_user
):
    Athlete.objects.create(
        sport=sport,
        agent=other_agent_user.agent_profile,
        full_name="Jane Smith",
        birth_date=date(1992, 2, 2),
        nationality="US",
        bio="Other bio",
        social_links={"twitter": "jane_smith"},
    )

    api_client.force_authenticate(agent_user)
    url = reverse("my-athletes")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(athlete.id)


@pytest.mark.django_db
def test_my_athletes_view_denies_non_agent_access(api_client, user_model):
    collaborator = user_model.objects.create_user(
        email="collab@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )

    api_client.force_authenticate(collaborator)
    url = reverse("my-athletes")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_list_requires_authentication(athlete):
    client = APIClient()
    url = reverse("athlete-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_list_forbidden_for_agents(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-list")
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
    url = reverse("athlete-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["full_name"] == athlete.full_name
    assert "bio" in response.data[0]


@pytest.mark.django_db
def test_athlete_retrieve_requires_authentication(athlete):
    client = APIClient()
    url = reverse("athlete-detail", kwargs={"pk": athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_retrieve_authenticated_success(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-detail", kwargs={"pk": athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["full_name"] == athlete.full_name


@pytest.mark.django_db
def test_athlete_retrieve_allows_collaborator(
    athlete, owner_user, organisation_subscription
):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    url = reverse("athlete-detail", kwargs={"pk": athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["full_name"] == athlete.full_name


@pytest.mark.django_db
def test_athlete_create_requires_agent_user(user_model, sport):
    client = APIClient()
    user = user_model.objects.create_user(
        email="organisation@example.com",
        password="pass1234",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    client.force_authenticate(user=user)
    url = reverse("athlete-list")
    response = client.post(
        url,
        {
            "sport_id": sport.id,
            "full_name": "Blocked User",
            "birth_date": "1999-09-09",
            "nationality": "FR",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_create_success(agent_user, sport):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-list")
    response = client.post(
        url,
        {
            "sport_id": sport.id,
            "full_name": "Created Athlete",
            "birth_date": "2001-01-01",
            "nationality": "US",
            "bio": "New bio",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Athlete.objects.filter(full_name="Created Athlete").exists()


@pytest.mark.django_db
def test_athlete_update_requires_owner(athlete, other_agent_user, sport):
    client = APIClient()
    client.force_authenticate(user=other_agent_user)
    url = reverse("athlete-detail", kwargs={"pk": athlete.id})
    response = client.patch(url, {"bio": "Attempted update"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_update_success(athlete, agent_user):
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-detail", kwargs={"pk": athlete.id})
    response = client.patch(url, {"bio": "Updated via API"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    athlete.refresh_from_db()
    assert athlete.bio == "Updated via API"


@pytest.mark.django_db
def test_sport_list_view_orders_by_name():
    Sport.objects.create(name="Z Sport")
    Sport.objects.create(name="A Sport")
    client = APIClient()
    response = client.get(reverse("sports-list"))
    assert response.status_code == status.HTTP_200_OK
    names = [item["name"] for item in response.data]
    assert names == sorted(names)


@pytest.mark.django_db
def test_athlete_viewset_default_permissions(agent_user):
    view = AthleteViewSet()
    view.action = "destroy"
    request = APIRequestFactory().delete("/")
    request.user = agent_user
    view.request = request
    permissions_list = view.get_permissions()
    assert len(permissions_list) == 2
    assert all(
        isinstance(item, permissions.BasePermission) for item in permissions_list
    )


@pytest.mark.django_db
def test_agent_create_athlete_limit_enforced(agent_user, sport):
    plan = SubscriptionPlan.objects.create(
        code="agent-free-test",
        name="Agent Free Test",
        price="0.00",
        features={"max_athletes": 1},
    )
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=aware_datetime(date(2025, 1, 1)),
        current_period_end=aware_datetime(date(2025, 12, 31)),
    )

    Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Initial Athlete",
        birth_date=date(1990, 1, 1),
        nationality="FR",
    )
    assert Athlete.objects.filter(agent=agent_user.agent_profile).count() == 1

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-list")
    payload = {
        "sport_id": sport.id,
        "full_name": "Second Athlete",
        "birth_date": "1992-02-02",
        "nationality": "US",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "max_athletes"


@pytest.mark.django_db
def test_agent_create_athlete_requires_plan_slot(agent_user, sport):
    plan = SubscriptionPlan.objects.create(
        code="agent-zero-slot",
        name="Agent Zero Slot",
        price="0.00",
        features={"max_athletes": 0},
    )
    Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=aware_datetime(date(2025, 1, 1)),
        current_period_end=aware_datetime(date(2025, 12, 31)),
    )

    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-list")
    payload = {
        "sport_id": sport.id,
        "full_name": "Blocked Athlete",
        "birth_date": "1993-03-03",
        "nationality": "US",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["required_feature"] == "max_athletes"


@pytest.mark.django_db
def test_athlete_serializer_rejects_cross_sport_disciplines(agent_user, sport):
    other_sport = Sport.objects.create(
        name="Swimming", emoji="🏊", category=Sport.Category.INDIVIDUAL
    )
    other_discipline = SportDiscipline.objects.create(
        sport=other_sport,
        name="200m Medley",
        description="All strokes",
    )
    factory = APIRequestFactory()
    request = factory.post("/api/athletes/")
    request.user = agent_user
    serializer = AthleteSerializer(
        data={
            "sport_id": sport.id,
            "full_name": "Cross Disc Athlete",
            "birth_date": "1993-03-03",
            "nationality": "FR",
            "discipline_ids": [str(other_discipline.id)],
        },
        context={"request": request},
    )
    assert not serializer.is_valid()
    assert "discipline_ids" in serializer.errors


@pytest.mark.django_db
def test_athlete_update_disciplines(agent_user, athlete, sport):
    new_discipline = sport.disciplines.get(name="Streetball")
    factory = APIRequestFactory()
    request = factory.patch("/api/athletes/")
    request.user = agent_user
    serializer = AthleteSerializer(
        athlete,
        data={"discipline_ids": [str(new_discipline.id)]},
        context={"request": request},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert list(updated.disciplines.values_list("name", flat=True)) == ["Streetball"]
