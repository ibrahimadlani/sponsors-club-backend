"""Views powering the payments API."""

# pylint: disable=no-member

import logging
from datetime import datetime

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from organisations.models import Collaborator
from users.models import AgentProfile

from core.feature_matrix import AGENT_FEATURES, COLLABORATOR_FEATURES
from core.permissions import (
    agent_meets_requirement,
    collaborator_meets_requirement,
    requirement_denied_payload,
)

from .models import Subscription, SubscriptionPlan
from .serializers import (
    SubscriptionCreateSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
)

logger = logging.getLogger(__name__)


class PlanListView(APIView):
    """List active subscription plans."""

    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):  # pylint: disable=unused-argument
        """Return all active plans ordered by price."""

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)


class SubscriptionCreateView(APIView):
    """Create a subscription for the requesting user."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """Validate payload and create a subscription."""

        del args, kwargs

        serializer = SubscriptionCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        subscription = serializer.save()
        return Response(
            SubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )


class MySubscriptionView(APIView):
    """Retrieve or cancel the authenticated user's subscription."""

    permission_classes = (permissions.IsAuthenticated,)

    def get_subscription(self, request):
        """Fetch the most relevant active subscription for the user."""

        user = request.user
        active_statuses = (
            Subscription.Status.ACTIVE,
            Subscription.Status.PAST_DUE,
            Subscription.Status.INCOMPLETE,
        )

        queryset = Subscription.objects.filter(status__in=active_statuses)

        try:
            agent_profile = user.agent_profile
        except AgentProfile.DoesNotExist:  # type: ignore[attr-defined]
            agent_profile = None

        if agent_profile:
            agent_subscription = (
                queryset.filter(agent=agent_profile)
                .order_by('-created_at')
                .first()
            )
            if agent_subscription:
                return agent_subscription

        organisation_ids = list(
            Collaborator.objects.filter(user=user).values_list('organisation_id', flat=True)
        )
        if organisation_ids:
            org_subscription = (
                queryset.filter(organisation_id__in=organisation_ids)
                .order_by('-created_at')
                .first()
            )
            if org_subscription:
                return org_subscription
        return None

    def get(self, request, *args, **kwargs):
        """Return the user's subscription details."""

        del args, kwargs

        subscription = self.get_subscription(request)
        if subscription is None:
            return Response(
                {'detail': 'No active subscription found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SubscriptionSerializer(subscription).data)

    def delete(self, request, *args, **kwargs):
        """Cancel the user's subscription when permitted."""

        del args, kwargs

        subscription = self.get_subscription(request)
        if subscription is None:
            return Response(
                {'detail': 'No active subscription found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if subscription.agent_id:
            requirement = AGENT_FEATURES['subscription_management']
            if not agent_meets_requirement(request.user, requirement):
                payload = requirement_denied_payload(
                    requirement,
                    'Upgrade required to manage your agent subscription.',
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)
        elif subscription.organisation_id:
            requirement = COLLABORATOR_FEATURES['organisation_subscription_management']
            if not collaborator_meets_requirement(request.user, requirement):
                payload = requirement_denied_payload(
                    requirement,
                    'Upgrade required to manage organisation subscriptions.',
                )
                return Response(payload, status=status.HTTP_403_FORBIDDEN)

        subscription.status = Subscription.Status.CANCELED
        subscription.current_period_end = timezone.now()
        subscription.save(update_fields=['status', 'current_period_end', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class StripeWebhookView(APIView):
    """Ingest Stripe webhook events and sync subscription state."""

    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        """Process the Stripe webhook payload."""

        del args, kwargs

        event_type = request.data.get('type')
        data_object = request.data.get('data', {}).get('object', {})
        subscription_id = data_object.get('id') or data_object.get('subscription')
        status_update = data_object.get('status')

        if not subscription_id:
            logger.warning(
                'Stripe webhook received without subscription id: %s',
                request.data,
            )
            return Response(
                {'detail': 'Missing subscription id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscription = Subscription.objects.filter(
            stripe_subscription_id=subscription_id,
        ).first()
        if not subscription:
            logger.warning('Stripe subscription %s not found.', subscription_id)
            return Response({'detail': 'Subscription not tracked.'}, status=status.HTTP_200_OK)

        if status_update and status_update in dict(Subscription.Status.choices):
            subscription.status = status_update
        if data_object.get('current_period_end'):
            subscription.current_period_end = datetime.fromtimestamp(
                data_object['current_period_end'],
                tz=timezone.utc,
            )
        subscription.save(update_fields=['status', 'current_period_end', 'updated_at'])

        logger.info(
            'Processed Stripe webhook %s for subscription %s',
            event_type,
            subscription_id,
        )
        return Response({'detail': 'Processed.'}, status=status.HTTP_200_OK)
