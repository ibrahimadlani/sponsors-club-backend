# Authentication & Account Lifecycle

The platform combines Django session authentication with JWT bearer tokens so staff tooling and third-party clients can share the same backend. Core wiring lives in the `users` app and is implemented with Django REST Framework (DRF) plus Simple JWT.

## Authentication stack

- **Enabled backends** – DRF registers `SessionAuthentication` and `JWTAuthentication`. Browsers reuse Django sessions while SPAs and mobile clients present `Authorization: Bearer <token>`.
- **Identity store** – The custom `users.User` model carries account metadata and links to optional `AgentProfile` records, which are used by the entitlement system.
- **URL surface** – `users.urls` exposes registration, login/refresh, profile, roles, and entitlements under `/api/users/`.

## Registration workflow

1. `POST /api/users/register/` (handled by `RegisterView`) validates input with `RegisterSerializer`.
2. The serializer creates the user, hashes the password, and provisions an `AgentProfile` when the account type is `AGENT`.
3. Agent profile names are derived from the supplied first/last name or fall back to the email address.
4. The response uses `UserSerializer`, so clients always receive a consistent representation.

```http
POST /api/users/register/
Content-Type: application/json

{
  "email": "agent@example.com",
  "password": "test1234",
  "account_type": "AGENT",
  "first_name": "Ada",
  "last_name": "Lovelace"
}
```

## JWT lifecycle

- **Login** – `POST /api/users/login/` hits `TokenObtainPairWithProfileView`. On success it issues an `access` and `refresh` token pair enriched with identity claims (see below).
- **Refresh** – `POST /api/users/refresh/` exchanges a valid refresh token for a new access token using Simple JWT's `TokenRefreshView`.
- **Logout** – There is no server-side revocation list; clients should discard refresh tokens or wait for them to expire.

### Custom access-token claims
- `email`, `prenom`, `nom`, and `role` for identity.
- Optional `plan` when the user has an associated subscription plan hint.
- `agent_has_athlete` for agents managing at least one athlete.
- `collaborator_has_org`:
  - Agents receive `false` unless they are also collaborators (claim omitted in that case).
  - Collaborators receive a boolean based on membership.

## Self-service endpoints

- **`GET /api/users/me/`** – Returns the authenticated user. `PUT/PATCH` accepts `MeUpdateSerializer`, updating contact details and `AgentProfile.is_self_represented` when supplied.
- **`GET /api/users/me/roles/`** – Uses `RolesDataBuilder` to return `is_agent`, a summarised `agent_profile`, the first organisation collaboration, and a list of all collaborator organisation IDs.
- **`GET /api/users/me/entitlements/`** – Calls `feature_status_for_user` to enumerate every feature requirement for the current account type, including grant status, recommended plans, and upgrade URLs. Downstream apps use this data to surface upgrade CTAs.

All endpoints require authentication and support both cookie and bearer auth.

## Role derivation & entitlements

Roles are additive: registering as an agent creates the agent profile, while collaborator roles stem from `organisations.Collaborator` records (ownership, membership) created via the organisations app. Entitlements read subscription metadata from the `payments` app to decide whether operations such as messaging, follows, or contract workflows should proceed.
