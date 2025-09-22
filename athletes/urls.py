"""URL routes for athlete resources."""

# Routers keep endpoint definitions declarative and in sync with the viewset.

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AthleteViewSet, MyAthletesView, SportListView

# DefaultRouter wires up standard CRUD endpoints such as /athletes/<id>/.
router = DefaultRouter()
router.register(r"athletes", AthleteViewSet, basename="athlete")

urlpatterns = [
    path("", include(router.urls)),
    path("me/athletes/", MyAthletesView.as_view(), name="my-athletes"),
    path("sports/", SportListView.as_view(), name="sports-list"),
]
