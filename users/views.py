"""API views for user registration and self-service endpoints."""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import feature_status_for_user
from .serializers import (
    EmailVerificationConfirmSerializer,
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


class VerifyEmailView(APIView):
    """Allow users to confirm their email address via verification token."""

    permission_classes = (permissions.AllowAny,)

    def post(self, request, *_args, **_kwargs):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Email address verified."})


class TokenObtainPairWithProfileSerializer(TokenObtainPairSerializer):
    """Extend JWT payload with user profile claims.

    Adds first/last names, email, account role, and plan when available.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Core identity
        token["email"] = getattr(user, "email", None)
        token["prenom"] = getattr(user, "first_name", None)
        token["nom"] = getattr(user, "last_name", None)
        # Business context
        token["role"] = getattr(user, "account_type", None)
        # Optional: attach subscription/plan info if present on user
        plan = getattr(user, "plan", None)
        if plan is None:
            # Fallback: check a related profile or organisation membership if your domain uses it
            # Keep minimal and safe by not querying extra relations eagerly.
            plan = getattr(getattr(user, "agent_profile", None), "plan", None)
        if plan is not None:
            token["plan"] = plan

        # Role-based flags
        try:
            from athletes.models import Athlete
            from organisations.models import Collaborator
        except Exception:  # pragma: no cover - import guards for optional apps
            Athlete = None  # type: ignore
            Collaborator = None  # type: ignore

        role = token.get("role")
        if role == getattr(user.__class__.AccountType, "AGENT", "AGENT"):
            has_athlete = False
            if hasattr(user, "agent_profile") and user.agent_profile_id:
                if Athlete is not None:
                    has_athlete = Athlete.objects.filter(agent=user.agent_profile).exists()
            token["agent_has_athlete"] = has_athlete
        elif role == getattr(user.__class__.AccountType, "COLLABORATOR", "COLLABORATOR"):
            # Only collaborators get this claim
            is_collaborator = False
            if Collaborator is not None:
                is_collaborator = Collaborator.objects.filter(user=user).exists()
            token["collaborator_has_org"] = is_collaborator
        return token


class TokenObtainPairWithProfileView(TokenObtainPairView):
    serializer_class = TokenObtainPairWithProfileSerializer
