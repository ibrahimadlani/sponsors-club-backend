"""URL routing for the payments API."""

from django.urls import path

from .views import (
    MarketplaceStripeWebhookView,
    MySubscriptionView,
    PlanListView,
    PlatformFeeDetailView,
    StripeCheckoutSessionView,
    StripeWebhookView,
    SubscriptionCreateView,
)

urlpatterns = [
    # Legacy SaaS subscription endpoints (kept for billing history)
    path("plans/", PlanListView.as_view(), name="payments-plans"),
    path("subscriptions/", SubscriptionCreateView.as_view(), name="payments-subscribe"),
    path(
        "subscriptions/me/",
        MySubscriptionView.as_view(),
        name="payments-subscription-me",
    ),
    path(
        "stripe/webhook/",
        StripeWebhookView.as_view(),
        name="payments-stripe-webhook",
    ),
    path(
        "stripe/checkout-session/",
        StripeCheckoutSessionView.as_view(),
        name="payments-stripe-checkout",
    ),
    # Marketplace transactional fee endpoints
    path(
        "fees/<uuid:contract_id>/",
        PlatformFeeDetailView.as_view(),
        name="payments-platform-fee",
    ),
    path(
        "stripe/marketplace-webhook/",
        MarketplaceStripeWebhookView.as_view(),
        name="payments-marketplace-webhook",
    ),
]
