"""Tests for the deterministic seed management command."""

from __future__ import annotations

from io import StringIO

import pytest
from faker import Faker
from django.core.management import call_command

from analytics.models import AthleteSocialAccount, DailyStats, SocialPlatform
from athletes.models import Athlete, SportDiscipline
from core.management.commands.seed import Command
from organisations.models import Collaborator, Organisation
from users.models import AgentProfile


@pytest.mark.django_db
def test_seed_command_populates_requested_entities():
    """Running the command creates the requested volume of demo data."""
    output = StringIO()

    baseline_agents = AgentProfile.objects.count()
    baseline_organisations = Organisation.objects.count()
    baseline_owners = Collaborator.objects.filter(role=Collaborator.Role.OWNER).count()
    baseline_sports = SportDiscipline.objects.count()
    baseline_athletes = Athlete.objects.count()
    baseline_accounts = AthleteSocialAccount.objects.count()
    baseline_stats = DailyStats.objects.count()
    baseline_platforms = set(SocialPlatform.objects.values_list("name", flat=True))

    call_command(
        "seed",
        agents=2,
        organisations=1,
        sports=2,
        athletes=3,
        seed=2024,
        stdout=output,
    )

    message = output.getvalue().strip().splitlines()[-1]
    assert message == "Seed completed: 2 agents, 1 organisations, 2 sports, 3 athletes."

    assert AgentProfile.objects.count() == baseline_agents + 2
    assert Organisation.objects.count() == baseline_organisations + 1
    assert (
        Collaborator.objects.filter(role=Collaborator.Role.OWNER).count()
        == baseline_owners + 1
    )
    assert SportDiscipline.objects.count() == baseline_sports + 2
    assert Athlete.objects.count() == baseline_athletes + 3
    assert AthleteSocialAccount.objects.count() == baseline_accounts + 3
    assert DailyStats.objects.count() == baseline_stats + (3 * 5)

    expected_platforms = {choice for choice, _ in SocialPlatform.Platform.choices}
    current_platforms = set(SocialPlatform.objects.values_list("name", flat=True))
    assert expected_platforms.issubset(baseline_platforms | current_platforms)

    for athlete in Athlete.objects.all():
        assert athlete.agent is not None
        assert athlete.disciplines.exists()
        account = athlete.social_accounts.get()
        stats = account.daily_stats.order_by("date")
        assert stats.count() == 5
        assert all(item.top_post for item in stats)


@pytest.mark.django_db
def test_create_organisations_handles_zero_count():
    """The helper returns early when no organisations are requested."""
    faker = Faker()
    command = Command()

    organisations = command._create_organisations(faker, 0)

    assert organisations == []
    assert Organisation.objects.count() == 0
    assert Collaborator.objects.count() == 0


@pytest.mark.django_db
def test_create_athletes_requires_supporting_data():
    """The athlete helper refuses to run without agents or sports."""
    faker = Faker()
    command = Command()

    athletes_without_agents = command._create_athletes(faker, 3, [], [])
    assert athletes_without_agents == []
    assert Athlete.objects.count() == 0

    agents = command._create_agents(faker, 1)
    athletes_without_sports = command._create_athletes(faker, 1, agents, [])
    assert athletes_without_sports == []
    assert Athlete.objects.count() == 0


@pytest.mark.django_db
def test_create_athlete_stats_creates_accounts_and_daily_metrics():
    """Generating analytics creates a social account and five stats per athlete."""
    faker = Faker()
    command = Command()

    agents = command._create_agents(faker, 1)
    sports = command._create_sports(faker, 1)
    athletes = command._create_athletes(faker, 1, agents, sports)

    command._create_athlete_stats(faker, athletes)

    assert AthleteSocialAccount.objects.count() == 1
    assert DailyStats.objects.count() == 5
    account = AthleteSocialAccount.objects.select_related("platform").get()
    assert account.platform.name in dict(SocialPlatform.Platform.choices)
    assert account.daily_stats.count() == 5

    command._create_athlete_stats(faker, [])
    assert AthleteSocialAccount.objects.count() == 1
    assert DailyStats.objects.count() == 5
