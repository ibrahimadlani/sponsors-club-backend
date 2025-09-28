from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from analytics.models import AthleteSocialAccount, DailyStats, SocialPlatform
from analytics.services import reports
from athletes.models import Athlete, Sport, SportDiscipline


@pytest.fixture
@pytest.mark.django_db
def platform():
    return SocialPlatform.objects.create(
        name=SocialPlatform.Platform.INSTAGRAM,
        base_url="https://instagram.com",
    )


@pytest.fixture
@pytest.mark.django_db
def athlete(agent_user):
    sport = Sport.objects.create(
        name="Freestyle", emoji="🛹", category=Sport.Category.INDIVIDUAL
    )
    SportDiscipline.objects.create(
        sport=sport,
        name="Street",
        description="Street discipline",
        is_olympic=False,
    )
    return Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Jordan Ride",
        birth_date=date(1998, 3, 2),
        nationality="US",
    )


@pytest.fixture
@pytest.mark.django_db
def account(athlete, platform):
    return AthleteSocialAccount.objects.create(
        athlete=athlete,
        platform=platform,
        username="jordan",
        external_id="insta-1",
        is_active=True,
    )


@pytest.fixture
@pytest.mark.django_db
def stats(account):
    base = date.today() - timedelta(days=2)
    stats = []
    for offset in range(3):
        stats.append(
            DailyStats.objects.create(
                account=account,
                date=base + timedelta(days=offset),
                followers=1000 + offset * 50,
                following=200,
                posts_count=offset + 1,
                likes=150 + offset * 10,
                comments=10 + offset,
                shares=5,
                views=1000 + offset * 100,
                watch_time=42.0,
                top_post={
                    "post_id": f"post-{offset}",
                    "likes": 150 + offset * 10,
                    "comments": 10 + offset,
                    "engagement_rate": 3.5 + offset,
                },
            )
        )
    return stats


def _stub_stat(**kwargs):
    return SimpleNamespace(**kwargs)


def test_parse_range_defaults(monkeypatch):
    fixed_today = date(2023, 6, 30)
    monkeypatch.setattr(
        timezone, "now", lambda: datetime(2023, 6, 30, tzinfo=timezone.utc)
    )
    result = reports.parse_range(None)
    assert result.label == "last_30_days"
    assert result.end == fixed_today
    assert result.start == fixed_today - timedelta(days=29)


def test_parse_range_numeric(monkeypatch):
    monkeypatch.setattr(
        timezone, "now", lambda: datetime(2023, 6, 30, tzinfo=timezone.utc)
    )
    result = reports.parse_range("7d")
    assert result.label == "last_7_days"
    assert result.start == date(2023, 6, 24)


def test_followers_growth_handles_empty():
    assert reports.followers_growth([]) == 0


def test_followers_growth_returns_difference():
    stats = [_stub_stat(followers=100), _stub_stat(followers=140)]
    assert reports.followers_growth(stats) == 40


def test_average_engagement_rate_handles_empty():
    assert reports.average_engagement_rate([]) == 0.0


def test_average_engagement_rate_rounds():
    stats = [_stub_stat(engagement_rate=2.333), _stub_stat(engagement_rate=2.666)]
    assert reports.average_engagement_rate(stats) == 2.5


def test_total_posts_sums_values():
    stats = [_stub_stat(posts_count=1), _stub_stat(posts_count=4)]
    assert reports.total_posts(stats) == 5


def test_top_post_returns_none_when_missing():
    assert reports.top_post([_stub_stat(top_post=None)]) is None


def test_top_post_returns_best():
    stats = [
        _stub_stat(top_post={"post_id": "1", "engagement_rate": 2.1, "likes": 10, "comments": 1}),
        _stub_stat(top_post={"post_id": "2", "engagement_rate": 3.6, "likes": 12, "comments": 2}),
    ]
    best = reports.top_post(stats)
    assert best["post_id"] == "2"
    assert best["engagement_rate"] == 3.6


def test_graph_points_rounds_values():
    stats = [
        _stub_stat(date=date(2023, 6, 1), followers=100, engagement_rate=2.3456),
    ]
    points = reports.graph_points(stats)
    assert points == [
        {"date": date(2023, 6, 1), "followers": 100, "engagement_rate": 2.35}
    ]


@pytest.mark.django_db
def test_build_summary_payload(account, stats):
    period = reports.DateRange("last_3_days", stats[0].date, stats[-1].date)
    payload = reports.build_summary_payload(account.athlete_id, account, stats, period)
    assert payload["summary"]["followers_growth"] == 100.0
    assert payload["platform"] == "Instagram"
    assert payload["top_post"]["post_id"] == "post-2"


@pytest.mark.django_db
def test_collect_platform_metrics(account, stats):
    metrics = reports.collect_platform_metrics(account.athlete)
    assert set(metrics.keys()) == {"Instagram"}
    assert metrics["Instagram"]["followers"] == float(stats[-1].followers)


@pytest.mark.django_db
def test_summarise_totals_calculates_averages():
    metrics = {
        "Instagram": {"followers": 100.0, "engagement_rate": 2.2, "posts_count": 5.0, "likes": 50.0, "comments": 4.0},
        "TikTok": {"followers": 150.0, "engagement_rate": 1.8, "posts_count": 3.0, "likes": 30.0, "comments": 2.0},
    }
    totals = reports.summarise_totals(metrics)
    assert totals["followers"] == 250.0
    assert totals["engagement_rate"] == 2.0
    assert totals["likes"] == 80.0


@pytest.mark.django_db
def test_build_comparison_payload(account, stats, agent_user, platform):
    other = Athlete.objects.create(
        sport=account.athlete.sport,
        agent=agent_user.agent_profile,
        full_name="Alex Second",
        birth_date=date(1997, 7, 7),
        nationality="CA",
    )
    other_account = AthleteSocialAccount.objects.create(
        athlete=other,
        platform=platform,
        username="alex",
        external_id="insta-2",
        is_active=True,
    )
    for offset in range(3):
        DailyStats.objects.create(
            account=other_account,
            date=stats[0].date + timedelta(days=offset),
            followers=900 + offset * 25,
            following=180,
            posts_count=offset + 1,
            likes=100 + offset * 5,
            comments=5 + offset,
            shares=1,
            views=800 + offset * 50,
            watch_time=12.0,
            top_post={"post_id": f"other-{offset}", "engagement_rate": 2.0 + offset},
        )
    payload = reports.build_comparison_payload(account.athlete, other)
    assert payload["primary"]["athlete_id"] == str(account.athlete.id)
    assert payload["comparison"]["totals"]["followers"] > 0
    assert "Instagram" in payload["comparison"]["platforms"]
