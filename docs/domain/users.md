# Users domain

## Purpose
The `users` app provides the platform-wide identity layer: custom user model, agent profiles, registration flows, JWT authentication, self-service profile management, role discovery, and feature entitlement endpoints. Other domain apps depend on it for authentication and collaboration lookups.

## Data model
- **`User`** – Email-as-username model with explicit `AccountType` choices (`AGENT`, `COLLABORATOR`). Stores profile fields (first/last name, phone, date of birth) and mirrors Django's hashed password into `password_hash` for compatibility with external tooling. Email is unique. The `(phone_country_code, phone_number)` pair is unique when both values are provided.
- **`AgentProfile`** – One-to-one extension for agent accounts that records `is_self_represented`, optional bio, and derives a display name from the linked user. Presence of a profile indicates the user should be treated as an agent in entitlements.

## Key workflows & serializers
- **`RegisterSerializer`** accepts either agent or collaborator registrations. Agent sign-ups automatically create an `AgentProfile`. Collaborator onboarding into organisations is managed through the `organisations` app.
- **`MeUpdateSerializer`** updates mutable fields on the authenticated user and can toggle `AgentProfile.is_self_represented` when supplied.
- **`RolesDataBuilder` / `RolesSerializer`** aggregate role information for `/me/roles/`, including whether the user is an agent, a summary of the agent profile, the first organisation collaboration, and an ordered list of all collaboration IDs. The builder performs two targeted queries (one for the profile, one `values_list` on `Collaborator`).
- **`MeEntitlementsView`** is a thin wrapper around `core.permissions.feature_status_for_user`, returning the evaluated feature flags plus upgrade metadata.
- **JWT views** (`TokenObtainPairWithProfileView`, `TokenRefreshView`) extend Simple JWT login with custom claims (see below).

## API surface (`/api/users/…`)
| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `POST` | `/register/` | Create an agent or collaborator account. | Public |
| `POST` | `/login/` | Obtain JWT access/refresh tokens. | Public |
| `POST` | `/refresh/` | Refresh a JWT token pair. | Public |
| `GET` | `/me/` | Retrieve the authenticated user's profile. | Authenticated |
| `PUT/PATCH` | `/me/` | Update core profile fields (agents can toggle representation). | Authenticated |
| `GET` | `/me/roles/` | Return aggregated role/collaboration metadata. | Authenticated |
| `GET` | `/me/entitlements/` | Return evaluated feature entitlements. | Authenticated |

All endpoints use DRF generics. There are no list endpoints here, so pagination is not applied.

## Custom JWT claims
- **Identity:** `email`, `prenom` (first name), `nom` (last name), `role`, optional `plan` hint when available.
- **Agents:** `agent_has_athlete` records whether the linked `AgentProfile` manages any athletes. `collaborator_has_org` is set to `False` unless the agent is also a collaborator; in that case the claim is omitted entirely.
- **Collaborators:** `collaborator_has_org` reflects whether the user holds at least one `Collaborator` record.

## `/me/roles/` response contract
```
{
  "is_agent": true | false,
  "agent_profile": {
    "id": "<uuid>",
    "name": "<display_name>",
    "is_self_represented": true | false
  } | null,
  "collaboration": "<organisation_uuid>" | null,
  "collaborations": ["<organisation_uuid>", …]
}
```
The first collaboration acts as the “primary” one for consumers that only need a single reference, while the list supports richer UI surfaces.

## Interactions with other domains
- Collaborator membership is owned by the `organisations` app. The users app never creates organisation records directly beyond collaborating with invitations.
- Feature entitlements are resolved through `core.permissions`, which inspects subscriptions stored by the `payments` app.

## Testing touchpoints
- Pytest fixtures in `conftest.py` provision `owner_user`, collaborators, and subscriptions used throughout the suite.
- Unit tests cover registration flows, JWT claim generation, and the roles/entitlements endpoints. When adding new fields ensure serializers and tests stay aligned.
