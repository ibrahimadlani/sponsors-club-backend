"""Router registration for contract endpoints."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ContractViewSet

router = DefaultRouter()
router.register(r"contracts", ContractViewSet, basename="contract")

urlpatterns = [
    path("", include(router.urls)),
]
