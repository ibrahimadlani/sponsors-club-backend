# Payments domain

## Overview
The payments app models subscription plans, tracks active subscriptions for
agents or organisations, and integrates with Stripe webhooks to keep statuses in
sync. It also exposes plan listings and subscription management APIs guarded by
plan-based entitlements.

## Data model
- **`SubscriptionPlan`** defines commercial offerings with pricing, currency,
  quota fields (`max_athletes`, `max_collaborators`), optional feature metadata,
  and Stripe product/price identifiers.
- **`Subscription`** represents an active subscription for either an
  organisation or an agent (mutually exclusive, enforced by a check constraint
  and model validation). It tracks status, period dates, and Stripe linkage.

## Serializers and workflows
- `SubscriptionPlanSerializer` returns public plan details.
- `SubscriptionSerializer` exposes subscription records with read-only scope.
- `SubscriptionCreateSerializer` validates plan availability and scope. It
  ensures only organisation owners may subscribe on behalf of their team,
  enforcing the `COLLABORATOR_FEATURES["organisation_subscription_management"]`
  requirement via `collaborator_meets_requirement()`. Agent subscriptions require
  the authenticated user to match the agent profile and reject duplicates. The
  serializer also parses optional `start_at` and `current_period_end` timestamps
  to seed billing cycles.

## Permissions and entitlements
- Plan listing is public.
- Creating subscriptions requires authentication and passes through the
  validations described above.
- `MySubscriptionView` retrieves the most relevant active subscription for the
  user (agent-first, falling back to organisations they collaborate with). The
  `DELETE` handler cancels the subscription only if the appropriate entitlement
  is granted:
  - Agents must satisfy `AGENT_FEATURES["subscription_management"]`.
  - Organisation collaborators must satisfy
    `COLLABORATOR_FEATURES["organisation_subscription_management"]`.

## Stripe webhook ingestion
`StripeWebhookView` accepts webhook payloads, extracts the Stripe subscription
ID, and updates local status and `current_period_end` when tracked. Missing or
unknown subscriptions return early with informative responses and log warnings.

## API surface
Routes are mounted under `/api/payments/`.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/plans/` | List active subscription plans ordered by price. | Public |
| `POST` | `/subscriptions/` | Create a subscription for an organisation or agent. | Authenticated with scope-specific requirements |
| `GET` | `/subscriptions/me/` | Retrieve the authenticated user's active subscription (agent or organisation). | Authenticated |
| `DELETE` | `/subscriptions/me/` | Cancel the active subscription if permitted. | Authenticated with cancellation feature |
| `POST` | `/stripe/webhook/` | Stripe webhook endpoint to sync subscription status updates. | Public (Stripe) |

No dedicated pagination classes are defined; list endpoints rely on DRF defaults.
