"""URL patterns for analytics endpoints."""

from django.urls import path

from .views import AthleteStatsBatchView, AthleteStatsTimeseriesView, AthleteStatsView

urlpatterns = [
    path(
        'athletes/<uuid:athlete_id>/stats/',
        AthleteStatsView.as_view(),
        name='athlete-stats',
    ),
    path(
        'athletes/<uuid:athlete_id>/stats/timeseries/',
        AthleteStatsTimeseriesView.as_view(),
        name='athlete-stats-timeseries',
    ),
    path(
        'analytics/athletes/batch/',
        AthleteStatsBatchView.as_view(),
        name='analytics-athletes-batch',
    ),
]
