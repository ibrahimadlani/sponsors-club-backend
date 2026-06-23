# Payments domain

## Overview

The `payments` app manages two distinct revenue models:

1. **SaaS subscriptions** — recurring plans for agents and organisations with
   quota-based feature access, integrated with Stripe billing.
2. **Marketplace transaction fees** — one-time platform fees triggered when a
   sponsorship contract reaches AGREEMENT status, gating DocuSign signing until
   the fee is paid.

## Data model

### SaaS subscriptions

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `SubscriptionPlan` | Commercial offering definition | `code` (unique), `name`, `price`, `currency`, `max_athletes`, `max_collaborators`, `features` (JSON), `stripe_product_id`, `stripe_price_id` |
| `Subscription` | Active subscription for an org or agent | `organisation` XOR `agent` (exactly one), `plan`, `status` (ACTIVE / PAST_DUE / CANCELED / INCOMPLETE / TRIALING / INCOMPLETE_EXPIRED / UNPAID), `start_at`, `current_period_end`, `stripe_customer_id`, `stripe_subscription_id` |

### Marketplace / transactional model

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `AthletePaymentAccount` | Stripe Connect Express account for an athlete | `athlete` (1:1), `stripe_account_id` (`acct_...`), `is_onboarded`, `charges_enabled`, `payouts_enabled` |
| `PlatformFee` | Invoice triggered at AGREEMENT status | `contract` (1:1), `fee_type`, `amount_due`, `status`, `stripe_payment_intent_id`, `paid_at`; `mark_paid()` |

#### `PlatformFee` fee calculation

| Counterpart mix | Fee type | Rule |
|----------------|---------|------|
| Any CASH counterpart | `CASH_COMMISSION` | `max(amount × 10 %, €10)` |
| Material only (no cash) | `MATERIAL_FIXED_FEE` | €49 flat |

Constants: `CASH_COMMISSION_RATE = 0.10`, `CASH_COMMISSION_MINIMUM = 10.00`,
`MATERIAL_FIXED_AMOUNT = 49.00`.

`PlatformFee.status` lifecycle:

```
PENDING → PAID      (via Stripe payment_intent.succeeded webhook)
         → DISPUTED (payment contested)
         → WAIVED   (staff override)
```

`mark_paid(stripe_payment_intent_id)` sets `status=PAID` and records `paid_at`.

**DocuSign paywall**: `contracts.views.init_signing()` checks
`PlatformFee.status == PAID` before creating the envelope. A PENDING fee returns
`HTTP 402` with the fee details so the client can redirect to the payment flow.

`generate_platform_fee()` on `Contract` is idempotent: calling it again on an
already-PAID fee is a no-op.

## Serializers and workflows

- `SubscriptionPlanSerializer` — read-only plan details for the public plan listing.
- `SubscriptionSerializer` — read-only subscription record.
- `SubscriptionCreateSerializer` — validates plan availability and scope:
  - Organisation owners must satisfy `COLLABORATOR_FEATURES["organisation_subscription_management"]`.
  - Agent subscriptions must match the authenticated user's agent profile and reject duplicates.
- `PlatformFeeSerializer` — exposes fee details to the client for the payment redirect.

## Permissions & entitlements

- Plan listing is **public**.
- Subscription creation requires authentication with scope-specific requirements (see above).
- `MySubscriptionView` returns the most relevant active subscription (agent-first,
  then collaborator organisations).
- Subscription cancellation checks:
  - Agents: `AGENT_FEATURES["subscription_management"]`
  - Collaborators: `COLLABORATOR_FEATURES["organisation_subscription_management"]`

## API endpoints

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| `GET` | `/api/payments/plans/` | Public | List active subscription plans ordered by price |
| `POST` | `/api/payments/subscriptions/` | Required | Create a subscription (org or agent) |
| `GET` | `/api/payments/subscriptions/me/` | Required | Retrieve authenticated user's active subscription |
| `DELETE` | `/api/payments/subscriptions/me/` | Required | Cancel subscription (feature gate applies) |
| `POST` | `/api/payments/stripe/checkout-session/` | Required | Create a Stripe Checkout session |
| `POST` | `/api/payments/stripe/webhook/` | Public (Stripe) | Sync subscription status from Stripe events |
| `GET` | `/api/payments/fees/<uuid>/` | Required | Retrieve platform fee for a contract |
| `POST` | `/api/payments/stripe/marketplace-webhook/` | Public (Stripe) | Handle Stripe Connect payment events (marketplace fees) |

## Stripe webhook events handled

| Event | Handler | Action |
|-------|---------|--------|
| `customer.subscription.updated` | `StripeWebhookView` | Sync `status` and `current_period_end` |
| `customer.subscription.deleted` | `StripeWebhookView` | Mark subscription as CANCELED |
| `payment_intent.succeeded` | `MarketplaceStripeWebhookView` | Call `mark_paid()` on matching `PlatformFee` |

## Key workflows

1. **Organisation subscribes** — Owner calls `POST /subscriptions/` with a `plan_code`;
   serializer validates entitlements and creates the subscription record. Stripe
   Checkout redirects for card capture.
2. **Subscription sync** — Stripe emits `customer.subscription.*` events;
   `StripeWebhookView` updates `status` and period dates.
3. **Contract fee trigger** — At AGREEMENT status, `Contract.generate_platform_fee()`
   creates a PENDING `PlatformFee`. The client is redirected to a payment page.
4. **Fee payment** — User pays via Stripe; `MarketplaceStripeWebhookView` receives
   `payment_intent.succeeded`, finds the fee by `stripe_payment_intent_id`, and
   calls `mark_paid()`. DocuSign signing is now unblocked.

## Dependencies

**Requires:** `organisations` (Organisation, Collaborator), `users` (User, AgentProfile)

**Used by:** `core` (feature entitlement matrix reads `features` JSON from active plan),
`contracts` (PlatformFee gating on `init_signing`)
