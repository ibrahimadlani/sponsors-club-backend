"""URL configuration for the users API endpoints."""

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    MeEntitlementsView,
    MeRolesView,
    MeView,
    RegisterView,
    UserBySlugView,
    VerifyEmailView,
)

app_name = "users"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("me/roles/", MeRolesView.as_view(), name="me_roles"),
    path("me/entitlements/", MeEntitlementsView.as_view(), name="me_entitlements"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path("slug/<slug:slug>/", UserBySlugView.as_view(), name="detail_by_slug"),
]
