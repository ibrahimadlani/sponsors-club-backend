"""API views for user registration and self-service endpoints."""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import feature_status_for_user
from .serializers import (
    MeUpdateSerializer,
    RegisterSerializer,
    RolesDataBuilder,
    RolesSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Public endpoint allowing creation of a new user account."""

    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        """Persist a new user and return the serialized representation."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = UserSerializer(user, context=self.get_serializer_context()).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class MeView(generics.RetrieveUpdateAPIView):
    """Authenticated view for retrieving or updating the current user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        """Return serializer tailored to read or update operations."""
        if self.request.method in ("PUT", "PATCH"):
            return MeUpdateSerializer
        return UserSerializer

    def get_object(self):
        """Return the authenticated user instance."""
        return self.request.user


class MeRolesView(APIView):
    """Provide information about the roles associated with the user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *_args, **_kwargs):
        """Return a structured payload describing the user's roles."""
        payload = RolesDataBuilder(request.user).build()
        serializer = RolesSerializer(payload)
        return Response(serializer.data)


class MeEntitlementsView(APIView):
    """Expose the feature entitlements granted to the authenticated user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *_args, **_kwargs):
        """Return the current user's feature entitlements and upgrade guidance."""
        user = request.user
        features = feature_status_for_user(user)
        return Response(
            {
                "account_type": getattr(user, "account_type", None),
                "features": features,
            }
        )
