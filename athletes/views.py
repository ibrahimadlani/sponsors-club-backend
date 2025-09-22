"""Views for athlete CRUD operations and sport listings."""

# These views intentionally keep business rules inside serializers and
# permissions so that they remain easy to reason about in tests.

from rest_framework import generics, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import get_agent_profile

from .models import Athlete, Sport
from .permissions import CanViewAthlete, IsAgentUser, IsAthleteOwner, IsCollaboratorUser
from .serializers import AthleteSerializer, SportSerializer


class AthleteViewSet(viewsets.ModelViewSet):
    """Provide list/retrieve/create/update/delete operations for athletes.

    The viewset leans on DRF's default mixins for data persistence while
    delegating domain checks to serializers and permission classes.
    """

    queryset = Athlete.objects.select_related("sport", "agent__user").all()

    def get_serializer_class(self):
        """Return the serializer used for the current request cycle.

        Returns:
            type[serializers.Serializer]: Serializer class responsible for
            validation and transformation of athlete payloads.
        """
        return AthleteSerializer

    def get_permissions(self):
        """Supply action-specific permission combinations.

        Returns:
            list[permissions.BasePermission]: Instantiated permission classes
            appropriate for the action being executed.
        """
        # Choosing permissions per action keeps the API surface expressive while
        # preventing over-privileged access for collaborators.
        if self.action == "list":
            return [permissions.IsAuthenticated(), IsCollaboratorUser()]
        if self.action == "retrieve":
            return [permissions.IsAuthenticated(), CanViewAthlete()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsAgentUser()]
        if self.action in ("update", "partial_update"):
            return [permissions.IsAuthenticated(), IsAthleteOwner()]
        if self.action == "destroy":
            return [permissions.IsAuthenticated(), IsAthleteOwner()]
        return super().get_permissions()

    def perform_create(self, serializer):
        """Persist a new athlete instance.

        Args:
            serializer (rest_framework.serializers.Serializer): Serializer with
                validated athlete data.
        """
        # Serializers enforce business limits such as plan-based quotas.
        serializer.save()

    def perform_update(self, serializer):
        """Persist changes to an existing athlete instance.

        Args:
            serializer (rest_framework.serializers.Serializer): Serializer with
                validated updates for the athlete.
        """
        serializer.save()


class MyAthletesView(generics.ListAPIView):
    """List the athletes owned by the authenticated agent."""

    serializer_class = AthleteSerializer
    permission_classes = (permissions.IsAuthenticated, IsAgentUser)

    def get_queryset(self):
        """Return the queryset restricted to the agent's own athletes.

        Returns:
            django.db.models.QuerySet: Athlete records owned by the requesting
            agent, including related sport and agent user data.
        """

        agent_profile = get_agent_profile(self.request.user)
        if agent_profile is None:
            # Returning ``none()`` avoids leaking data when an agent profile is
            # missing or misconfigured.
            return Athlete.objects.none()
        return Athlete.objects.filter(agent=agent_profile).select_related(
            "sport", "agent__user"
        )


class SportListView(APIView):
    """Return the list of sports supported by the platform."""

    permission_classes = (permissions.AllowAny,)

    def get(self, _request, *_args, **_kwargs):
        """Return all sports ordered alphabetically by name.

        Args:
            _request (rest_framework.request.Request): Incoming HTTP request.

        Returns:
            rest_framework.response.Response: JSON payload containing all sports
            sorted by name.
        """
        # Sorting in the database keeps the response stable regardless of how
        # entries were added in migrations or fixtures.
        sports = Sport.objects.all().order_by("name")
        serializer = SportSerializer(sports, many=True)
        return Response(serializer.data)
