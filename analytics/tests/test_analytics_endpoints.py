from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from analytics.models import AthleteSocialAccount, DailyStats, SocialPlatform
from athletes.models import Athlete, Sport


@pytest.fixture
def instagram_platform():
    return SocialPlatform.objects.create(
        name=SocialPlatform.Platform.INSTAGRAM,
        base_url="https://graph.facebook.com/instagram/",
    )


@pytest.fixture
def stats_sport():
    return Sport.objects.create(name="Volley", discipline="Team Sport")


@pytest.fixture
def stats_athlete(agent_user, stats_sport):
    return Athlete.objects.create(
        sport=stats_sport,
        agent=agent_user.agent_profile,
        full_name="Stat Athlete",
        birth_date=date(1995, 5, 5),
        nationality="FR",
    )


@pytest.fixture
def comparison_athlete(agent_user, stats_sport):
    return Athlete.objects.create(
        sport=stats_sport,
        agent=agent_user.agent_profile,
        full_name="Compare Athlete",
        birth_date=date(1994, 1, 12),
        nationality="GB",
    )


@pytest.fixture
def social_account(stats_athlete, instagram_platform):
    return AthleteSocialAccount.objects.create(
        athlete=stats_athlete,
        platform=instagram_platform,
        username="stat_athlete",
        external_id="ig-123",
        is_active=True,
    )


@pytest.fixture
def comparison_account(comparison_athlete, instagram_platform):
    return AthleteSocialAccount.objects.create(
        athlete=comparison_athlete,
        platform=instagram_platform,
        username="compare_athlete",
        external_id="ig-456",
        is_active=True,
    )


def _create_stats(account, start_followers=1000):
    base_date = date.today() - timedelta(days=2)
    for offset in range(3):
        DailyStats.objects.create(
            account=account,
            date=base_date + timedelta(days=offset),
            followers=start_followers + (offset * 50),
            following=400,
            posts_count=1,
            likes=200 + offset * 10,
            comments=20 + offset,
            shares=5,
            views=1000 + offset * 100,
            watch_time=123.4,
            top_post={
                "post_id": f"post-{offset}",
                "likes": 200 + offset * 10,
                "comments": 20 + offset,
                "engagement_rate": 4.5 + offset,
            },
        )


@pytest.mark.django_db
def test_stats_list_returns_paginated_data(agent_user, social_account):
    _create_stats(social_account)
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse("athlete-daily-stats", kwargs={"athlete_id": social_account.athlete.id})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 3
    assert response.data["results"][0]["followers"] == 1100


@pytest.mark.django_db
def test_summary_endpoint_returns_expected_payload(agent_user, social_account):
    _create_stats(social_account)
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse(
        "athlete-daily-stats-summary",
        kwargs={"athlete_id": social_account.athlete.id},
    )
    response = client.get(url, {"range": "30d", "platform": "instagram"})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["summary"]["followers_growth"] == 100.0
    assert response.data["summary"]["posts_count"] == 3.0
    assert response.data["top_post"]["post_id"] == "post-2"


@pytest.mark.django_db
def test_compare_endpoint(agent_user, social_account, comparison_account):
    _create_stats(social_account, start_followers=1200)
    _create_stats(comparison_account, start_followers=900)
    client = APIClient()
    client.force_authenticate(user=agent_user)
    url = reverse(
        "athlete-stats-compare",
        kwargs={
            "athlete_id": social_account.athlete.id,
            "other_id": comparison_account.athlete.id,
        },
    )
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["primary"]["totals"]["followers"] > response.data["secondary"]["totals"]["followers"]
