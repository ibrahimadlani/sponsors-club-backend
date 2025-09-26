from unittest.mock import call, patch

import pytest

from analytics.models import AthleteSocialAccount, SocialPlatform
from analytics import tasks
from athletes.models import Athlete, Sport, SportDiscipline


@pytest.fixture
@pytest.mark.django_db
def account(agent_user):
    sport = Sport.objects.create(
        name="Freestyle", emoji="🛹", category=Sport.Category.INDIVIDUAL
    )
    SportDiscipline.objects.create(
        sport=sport,
        name="Street",
        description="Street discipline",
        is_olympic=False,
    )
    platform = SocialPlatform.objects.create(
        name=SocialPlatform.Platform.INSTAGRAM,
        base_url="https://instagram.com",
    )
    athlete = Athlete.objects.create(
        sport=sport,
        agent=agent_user.agent_profile,
        full_name="Jordan Ride",
        birth_date="1998-03-02",
        nationality="US",
    )
    return AthleteSocialAccount.objects.create(
        athlete=athlete,
        platform=platform,
        username="jordan",
        external_id="insta-1",
        is_active=True,
    )


@pytest.mark.django_db
def test_fetch_account_stats_logs_and_returns_none(account, caplog):
    with caplog.at_level("INFO"):
        result = tasks.fetch_account_stats(account.id)
    assert result is None
    assert any("Fetching stats for" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_sync_all_accounts_iterates_over_accounts(account):
    second_platform = SocialPlatform.objects.create(
        name=SocialPlatform.Platform.YOUTUBE,
        base_url="https://youtube.com",
    )
    second = AthleteSocialAccount.objects.create(
        athlete=account.athlete,
        platform=second_platform,
        username="jordan-alt",
        external_id="insta-2",
        is_active=True,
    )
    with patch("analytics.tasks.fetch_account_stats", return_value=None) as fetch_mock:
        tasks.sync_all_accounts()
    assert fetch_mock.call_args_list == [call(account.id), call(second.id)]
