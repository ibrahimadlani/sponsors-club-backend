"""URL routes for the organisations app."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import OrganisationJoinView, OrganisationViewSet

router = DefaultRouter()
router.register(r"organisations", OrganisationViewSet, basename="organisation")

urlpatterns = [
    path("organisations/join/", OrganisationJoinView.as_view(), name="organisation-join"),
] + router.urls
