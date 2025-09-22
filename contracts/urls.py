"""URL routing for the contracts API endpoints."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClauseTemplateViewSet, ContractViewSet

# A router keeps the viewset wiring declarative and consistent with other apps.
router = DefaultRouter()
router.register(r"contracts", ContractViewSet, basename="contract")
router.register(r"clause-templates", ClauseTemplateViewSet, basename="clause-template")

urlpatterns = [
    path("", include(router.urls)),
]
