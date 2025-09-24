# Users domain

## Overview
The users app implements the custom user model, agent profiles, registration,
self-service profile updates, role aggregation, and feature entitlement
endpoints. It also exposes JWT login/refresh routes via DRF Simple JWT.

## Data model
- **`User`** extends Django's auth system with email-as-username, account type
  (`AGENT` or `COLLABORATOR`), profile metadata, and a mirrored `password_hash`
  field for legacy compatibility. `UserManager` powers email-based creation.
- **`AgentProfile`** is a one-to-one extension for agent accounts, storing a
  `display_name` and optional bio used throughout the platform.

## Serializers and workflows
- `RegisterSerializer` handles both agent and collaborator sign-ups. Agent
  registrations require a `display_name` and automatically create an
  `AgentProfile`. (Collaborator onboarding into organisations is managed by the
  organisations app.)
- `MeUpdateSerializer` updates core user fields and, when provided, synchronises
  the agent profile's `display_name`.
- `RolesDataBuilder` collects the authenticated user's collaborations and agent
  info for the `/me/roles/` endpoint, returning a shape validated by
  `RolesSerializer`.

## Feature entitlements
`MeEntitlementsView` calls `core.permissions.feature_status_for_user()` to return
all feature flags and upgrade guidance for the current user. This endpoint
underpins the entitlement-aware UX across the platform.

## API surface
Routes are mounted under `/api/users/`.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `POST` | `/register/` | Create an agent or collaborator account. | Public |
| `POST` | `/login/` | Obtain JWT access/refresh tokens (Simple JWT). | Public |
| `POST` | `/refresh/` | Refresh a JWT token pair. | Public |
| `GET` | `/me/` | Retrieve the authenticated user's profile. | Authenticated |
| `PUT/PATCH` | `/me/` | Update profile fields and, for agents, display name. | Authenticated |
| `GET` | `/me/roles/` | Return agent profile metadata and organisation collaborations. | Authenticated |
| `GET` | `/me/entitlements/` | Return the user's feature entitlements. | Authenticated |

All views leverage DRF generic classes with default pagination behaviour where
applicable (only listing endpoints paginate globally).
