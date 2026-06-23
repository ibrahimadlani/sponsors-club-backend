"""URL routes for athlete resources."""

# Routers keep endpoint definitions declarative and in sync with the viewset.

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AthleteBySlugView,
    AthletePhotoListView,
    AthleteViewSet,
    MyAthletesView,
    SportDisciplinesView,
    SportListView,
)

# DefaultRouter wires up standard CRUD endpoints such as /athletes/<id>/.
router = DefaultRouter()
router.register(r"athletes", AthleteViewSet, basename="athlete")

urlpatterns = [
    path("", include(router.urls)),
    path("me/athletes/", MyAthletesView.as_view(), name="my-athletes"),
    path("sports/", SportListView.as_view(), name="sports-list"),
    path(
        "sports/<uuid:sport_id>/disciplines/",
        SportDisciplinesView.as_view(),
        name="sport-disciplines",
    ),
    path(
        "athletes/slug/<slug:slug>/",
        AthleteBySlugView.as_view(),
        name="athlete-by-slug",
    ),
    path(
        "athletes/<uuid:athlete_id>/photos/",
        AthletePhotoListView.as_view(),
        name="athlete-photos",
    ),
]
