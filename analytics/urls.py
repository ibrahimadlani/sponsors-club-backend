"""URL patterns for analytics endpoints."""

from django.urls import path

from .views import (
    AthleteComparisonView,
    AthleteDailyStatsView,
    AthleteStatsSummaryView,
    FetchAccountStatsView,
    SyncAllAccountsView,
)

urlpatterns = [
    path(
        "analytics/athletes/<uuid:athlete_id>/stats/",
        AthleteDailyStatsView.as_view(),
        name="athlete-daily-stats",
    ),
    path(
        "analytics/athletes/<uuid:athlete_id>/stats/summary/",
        AthleteStatsSummaryView.as_view(),
        name="athlete-daily-stats-summary",
    ),
    path(
        "analytics/athletes/<uuid:athlete_id>/compare/<uuid:other_id>/",
        AthleteComparisonView.as_view(),
        name="athlete-stats-compare",
    ),
    path(
        "analytics/accounts/<uuid:account_id>/fetch/",
        FetchAccountStatsView.as_view(),
        name="analytics-account-fetch",
    ),
    path(
        "analytics/accounts/sync_all/",
        SyncAllAccountsView.as_view(),
        name="analytics-accounts-sync-all",
    ),
]
