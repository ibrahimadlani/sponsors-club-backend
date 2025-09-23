"""URL configuration for the follows API endpoints."""

from django.urls import path

from .views import AthleteFollowView, MyFollowsView

urlpatterns = [
    path(
        "athletes/<uuid:athlete_id>/follow/",
        AthleteFollowView.as_view(),
        name="athlete-follow",
    ),
    path("me/follows/", MyFollowsView.as_view(), name="my-follows"),
]
