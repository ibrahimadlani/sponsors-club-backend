"""Admin configuration for payments models."""

from django.contrib import admin

from .constants import PLAN_CORE_FIELDS
from .models import Subscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """Display subscription plan metadata in the admin panel."""

    list_display = (*PLAN_CORE_FIELDS, 'is_active')
    list_filter = ('currency', 'is_active')
    search_fields = ('code', 'name')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Surface subscription scope and timing details in admin."""

    list_display = (
        'plan',
        'organisation',
        'agent',
        'status',
        'start_at',
        'current_period_end',
    )
    list_filter = ('status', 'plan')
    search_fields = (
        'organisation__name',
        'agent__display_name',
        'stripe_customer_id',
        'stripe_subscription_id',
    )
