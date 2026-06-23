# `payments/` — SaaS subscription plans, Stripe billing, and marketplace transaction fees.

## Responsibility

- Define subscription plans with quota and feature metadata.
- Track active subscriptions for organisations and agents; sync status from Stripe.
- Manage Stripe Connect Express accounts for athlete payouts.
- Issue and collect one-time platform fees on sponsorship contracts (marketplace model).

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `SubscriptionPlan` | Commercial plan definition | `code` (unique), `price`, `max_athletes`, `max_collaborators`, `features` (JSON), `stripe_product_id`, `stripe_price_id` |
| `Subscription` | Active subscription record | `organisation` XOR `agent`, `plan`, `status` (ACTIVE / PAST_DUE / CANCELED / ...), `stripe_customer_id`, `stripe_subscription_id` |
| `AthletePaymentAccount` | Stripe Connect Express account | `athlete` (1:1), `stripe_account_id`, `is_onboarded`, `charges_enabled`, `payouts_enabled` |
| `PlatformFee` | Contract signing fee | `contract` (1:1), `fee_type` (CASH_COMMISSION / MATERIAL_FIXED_FEE), `amount_due`, `status` (PENDING / PAID / DISPUTED / WAIVED), `stripe_payment_intent_id`; `mark_paid()` |

### Platform fee rules

| Contract counterparts | Fee type | Formula |
|-----------------------|---------|---------|
| Any CASH counterpart | `CASH_COMMISSION` | `max(total_cash × 10 %, €10)` |
| Material only (no cash) | `MATERIAL_FIXED_FEE` | €49 flat |

The fee acts as a **DocuSign paywall**: `contracts.views.init_signing()` returns
`HTTP 402` if `PlatformFee.status != PAID`.

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/payments/plans/` | Public | `AllowAny` | List active subscription plans |
| `POST` | `/api/payments/subscriptions/` | Required | Scope-specific | Create a subscription |
| `GET` | `/api/payments/subscriptions/me/` | Required | `IsAuthenticated` | Get current user's subscription |
| `DELETE` | `/api/payments/subscriptions/me/` | Required | Feature gate | Cancel subscription |
| `POST` | `/api/payments/stripe/checkout-session/` | Required | `IsAuthenticated` | Create Stripe Checkout session |
| `POST` | `/api/payments/stripe/webhook/` | Public (Stripe) | — | Sync subscription status |
| `GET` | `/api/payments/fees/<uuid>/` | Required | `IsAuthenticated` | Get platform fee for a contract |
| `POST` | `/api/payments/stripe/marketplace-webhook/` | Public (Stripe) | — | Handle marketplace fee payments |

## Permissions & Roles

- **Plan listing** — public, no auth.
- **Subscription creation** — Organisation owners must satisfy
  `COLLABORATOR_FEATURES["organisation_subscription_management"]`; agents must
  match their own profile and have no existing subscription.
- **Subscription cancellation** — checked via `AGENT_FEATURES["subscription_management"]`
  (agents) or `COLLABORATOR_FEATURES["organisation_subscription_management"]` (orgs).

## Key Workflows

1. **Subscribe** — User selects a plan; `POST /subscriptions/` validates entitlements;
   `POST /stripe/checkout-session/` redirects to Stripe for card capture.
2. **Stripe sync** — Stripe emits `customer.subscription.*`; `StripeWebhookView` updates
   `status` and `current_period_end` on the matching `Subscription`.
3. **Contract fee** — At AGREEMENT status, `Contract.generate_platform_fee()` creates a
   PENDING `PlatformFee` record with the computed amount.
4. **Fee payment** — User pays via Stripe; `MarketplaceStripeWebhookView` receives
   `payment_intent.succeeded` and calls `PlatformFee.mark_paid()`. DocuSign signing
   is now unblocked.

## Dependencies

**Requires:** `organisations` (Organisation, Collaborator), `users` (User, AgentProfile),
`athletes` (Athlete for AthletePaymentAccount)

**Used by:** `core` (reads `Subscription.plan.features` for entitlement matrix),
`contracts` (checks PlatformFee.status before creating DocuSign envelope)
