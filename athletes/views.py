"""Views for athlete CRUD operations and sport listings."""

from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Athlete, Sport
from .permissions import CanViewAthlete, IsAgentUser, IsAthleteOwner, IsCollaboratorUser
from .serializers import AthleteSerializer, SportSerializer


class AthleteViewSet(viewsets.ModelViewSet):
    """Provide list/retrieve/create/update/delete operations for athletes."""

    queryset = Athlete.objects.select_related("sport", "agent__user").all()

    def get_serializer_class(self):
        """Return the serializer class used for this action."""
        return AthleteSerializer

    def get_permissions(self):
        """Supply action-specific permission combinations."""
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
        """Persist a new athlete instance."""
        serializer.save()

    def perform_update(self, serializer):
        """Persist changes to an existing athlete instance."""
        serializer.save()


class SportListView(APIView):
    """Return the list of sports supported by the platform."""

    permission_classes = (permissions.AllowAny,)

    def get(self, _request, *_args, **_kwargs):
        """Return all sports ordered alphabetically by name."""
        sports = Sport.objects.all().order_by("name")
        serializer = SportSerializer(sports, many=True)
        return Response(serializer.data)
