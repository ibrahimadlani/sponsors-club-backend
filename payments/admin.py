"""Admin configuration for payments models."""

# The admin site is primarily used by support staff to inspect plan offerings and
# troubleshoot customer subscriptions. The display configuration below surfaces
# the most relevant metadata for those workflows.

from django.contrib import admin

from .constants import PLAN_CORE_FIELDS
from .models import AthletePaymentAccount, PlatformFee, Subscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`SubscriptionPlan` records.

    Attributes:
        list_display (tuple[str, ...]): Fields rendered in the changelist view to
            help staff compare pricing tiers at a glance.
        list_filter (tuple[str, ...]): Filters that allow narrowing results by
            currency and active status.
        search_fields (tuple[str, ...]): Fields that support text search within
            the admin interface.
    """

    # Display core identifiers and pricing so operators can compare plans.
    list_display = (*PLAN_CORE_FIELDS, "is_active")
    list_filter = ("currency", "is_active")
    search_fields = ("code", "name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`Subscription` records.

    Attributes:
        list_display (tuple[str, ...]): Columns that reveal which plan a
            subscription references and who it is scoped to.
        list_filter (tuple[str, ...]): Quick filters for status and plan to
            diagnose billing issues.
        search_fields (tuple[str, ...]): Search fields enabling staff to find
            subscriptions by participant name or Stripe identifiers.
    """

    # Include plan and scope fields to quickly see who is billed for what tier.
    list_display = (
        "plan",
        "organisation",
        "agent",
        "status",
        "start_at",
        "current_period_end",
    )
    list_filter = ("status", "plan")
    search_fields = (
        "organisation__name",
        "agent__user__email",
        "agent__user__first_name",
        "agent__user__last_name",
        "stripe_customer_id",
        "stripe_subscription_id",
    )


@admin.register(AthletePaymentAccount)
class AthletePaymentAccountAdmin(admin.ModelAdmin):
    """Admin for Stripe Connect accounts linked to athletes."""

    list_display = (
        "athlete",
        "stripe_account_id",
        "is_onboarded",
        "charges_enabled",
        "payouts_enabled",
    )
    list_filter = ("is_onboarded", "charges_enabled", "payouts_enabled")
    search_fields = ("athlete__full_name", "stripe_account_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PlatformFee)
class PlatformFeeAdmin(admin.ModelAdmin):
    """Admin for marketplace invoices generated upon contract agreement."""

    list_display = ("contract", "fee_type", "amount_due", "status", "paid_at")
    list_filter = ("fee_type", "status")
    search_fields = ("contract__title", "stripe_payment_intent_id")
    readonly_fields = ("created_at", "updated_at", "paid_at")

    def has_add_permission(self, request):
        return False
