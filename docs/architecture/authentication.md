# Authentication & Account Lifecycle

This service combines Django session auth with JWT-based APIs so both the admin and SPA clients can interact with the same backend. The core wiring lives in the `users` app, backed by Django REST Framework (DRF) class-based views and SimpleJWT views for token issuance.

## Authentication stack

- **Enabled mechanisms** – DRF registers both `SessionAuthentication` and `JWTAuthentication`, letting browsers reuse login sessions while API clients rely on `Authorization: Bearer` headers.
- **User model** – A custom `users.User` model stores account metadata, links to optional `AgentProfile` records, and drives feature checks.
- **URL entry points** – `users.urls` exposes registration, JWT issuance, token refresh, and self-service endpoints under `/api/users/`.

## Registration workflow

1. `POST /api/users/register/` hits `RegisterView`, which permits anonymous access and validates payloads with `RegisterSerializer`.
2. Agent registrations automatically derive an initial `display_name` from the submitted first/last name (or email when absent);
   collaborator-specific fields remain optional and reserved for future onboarding flows.
3. During creation the serializer persists the `users.User`, hashes the password, and auto-creates an `AgentProfile` when the account type is `AGENT`.
4. The response is normalized through `UserSerializer`, returning the canonical user fields for immediate client use.

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

- **Login** – `POST /api/users/login/` delegates to SimpleJWT's `TokenObtainPairView`, issuing `access` and `refresh` tokens when the email/password pair is valid.
- **Refresh** – `POST /api/users/refresh/` exchanges a valid refresh token for a new access token via `TokenRefreshView`.
- **Revocation** – There is no server-side blacklist; clients should drop refresh tokens on logout or rely on their expiry window.

Tokens are standard SimpleJWT payloads, so extra claims can be injected later without touching local code.

## Self-service endpoints

- **`GET /api/users/me/`** – Returns the authenticated user. `PATCH`/`PUT` accepts `MeUpdateSerializer`, which updates contact fields and synchronizes the agent display name when relevant.
- **`GET /api/users/me/roles/`** – Aggregates roles via `RolesDataBuilder`, exposing agent profile details plus a list of organisation collaborations (id, name, role).
- **`GET /api/users/me/entitlements/`** – Calls `feature_status_for_user` to enumerate feature gates, returning the account type, grant status, upgrade links, and recommended plans. This powers in-app upgrade prompts.

All three endpoints require authentication and are safe to call with either session cookies or bearer tokens.

## Account roles & permissions

Role data and entitlements are additive: registering as an agent automatically provisions the agent profile, while collaborator roles derive from `organisations.Collaborator` memberships. Entitlements read subscription metadata from the payments subsystem so downstream apps (messaging, follows, contracts) can block actions when a plan is insufficient.
