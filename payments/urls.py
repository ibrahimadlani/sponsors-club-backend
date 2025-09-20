"""URL routing for the payments API."""

from django.urls import path

from .views import (
    MySubscriptionView,
    PlanListView,
    StripeCheckoutSessionView,
    StripeWebhookView,
    SubscriptionCreateView,
)

urlpatterns = [
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
]
