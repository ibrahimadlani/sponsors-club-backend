"""API views for serving analytics data."""

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from athletes.models import Athlete

from core.responses import error_response

from .models import AthleteSocialAccount, DailyStats
from .serializers import DailyStatsSerializer, DailyStatsSummarySerializer
from .services.reports import (
    build_comparison_payload,
    build_summary_payload,
    parse_range,
)
from .tasks import fetch_account_stats, sync_all_accounts


class DailyStatsPagination(PageNumberPagination):
    """Default pagination for daily stats endpoints."""

    page_size = 30
    max_page_size = 100


class AthleteDailyStatsView(generics.ListAPIView):
    """Expose paginated daily stats for a specific athlete."""

    serializer_class = DailyStatsSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = DailyStatsPagination

    def get_queryset(self):
        """Return daily stats filtered for the requested athlete.

        Returns:
            QuerySet: Ordered queryset ready for pagination.
        """

        athlete_id = self.kwargs["athlete_id"]
        queryset = DailyStats.objects.select_related(
            "account__athlete", "account__platform"
        ).filter(account__athlete_id=athlete_id)
        platform = self.request.query_params.get("platform")
        if platform:
            # Allow narrowing down results to a specific social network.
            queryset = queryset.filter(account__platform__name__iexact=platform)
        return queryset.order_by("-date", "-created_at")


class AthleteStatsSummaryView(APIView):
    """Return aggregated analytics for an athlete within a range."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, athlete_id):
        """Handle GET requests for the summary endpoint.

        Args:
            request: Incoming HTTP request carrying filters.
            athlete_id: UUID of the athlete being summarised.

        Returns:
            Response: JSON payload describing the requested period.
        """

        athlete = get_object_or_404(Athlete, id=athlete_id)
        date_range = parse_range(request.query_params.get("range"))
        platform = request.query_params.get("platform")
        accounts = athlete.social_accounts.filter(is_active=True).select_related(
            "platform"
        )
        if platform:
            # Limit the account set when the caller targets a specific platform.
            accounts = accounts.filter(platform__name__iexact=platform)
        account = accounts.first()
        if not account:
            return error_response(
                "No social accounts with stats available.",
                status.HTTP_404_NOT_FOUND,
                code="athlete_stats_account_missing",
            )

        stats_queryset = account.daily_stats.for_range(
            date_range.start, date_range.end
        ).order_by("date")
        stats = list(stats_queryset)
        payload = build_summary_payload(athlete.id, account, stats, date_range)
        serializer = DailyStatsSummarySerializer(payload)
        return Response(serializer.data)


class AthleteComparisonView(APIView):
    """Compare two athletes across their social platforms."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, athlete_id, other_id):
        """Return a comparison payload between two athletes.

        Args:
            request: Incoming HTTP request used mainly for authentication context.
            athlete_id: UUID of the primary athlete.
            other_id: UUID of the athlete being compared against the primary.

        Returns:
            Response: Structured comparison data for both athletes.
        """

        primary = get_object_or_404(Athlete, id=athlete_id)
        secondary = get_object_or_404(Athlete, id=other_id)
        payload = build_comparison_payload(primary, secondary)
        return Response(payload)


class FetchAccountStatsView(APIView):
    """Trigger a fetch for an individual social account."""

    permission_classes = (permissions.IsAdminUser,)

    def post(self, request, account_id):
        """Start a stat fetch for a single social account.

        Args:
            request: Request object used for authentication context.
            account_id: UUID of the account to refresh.

        Returns:
            Response: Acknowledgement that the sync request was enqueued.
        """

        account = get_object_or_404(AthleteSocialAccount, id=account_id)
        fetch_account_stats(account.id)
        return Response(
            {"detail": "Sync started for account."}, status=status.HTTP_202_ACCEPTED
        )


class SyncAllAccountsView(APIView):
    """Trigger a sync for all active social accounts."""

    permission_classes = (permissions.IsAdminUser,)

    def post(self, request):
        """Kick off a bulk synchronisation across every active account.

        Args:
            request: Request object carrying authentication context.

        Returns:
            Response: Confirmation that the background sync has started.
        """

        sync_all_accounts()
        return Response(
            {"detail": "Bulk sync started."}, status=status.HTTP_202_ACCEPTED
        )
