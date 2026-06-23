# `organisations/` — Partner organisations, collaborator rosters, and invitation system.

## Responsibility

- Organisation profiles with rich metadata (type, industry, social links, etc.).
- Collaborator membership: users join an organisation with OWNER or MEMBER role.
- Time-bound invitation codes with cryptographic randomness, rate limiting, and race
  condition protection.
- Ownership transfer between collaborators.

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Organisation` | Partner brand or entity | `name`, `slug`, `owner` (FK → Collaborator), `type`, `industry`, `social_links`, `sponsoring_focus`; `get_owner_id()`, `owner_user` property |
| `Collaborator` | User–organisation membership | `user`, `organisation`, `role` (OWNER / MEMBER), `job_title`; `clean()` (prevents multi-org), `delete()` (cascades to org when owner) |
| `OrganisationInvite` | Time-bound code for joining | `code`, `expires_at`, `is_used`, `used_by`, `created_by`; `status` property, `mark_used()`, `generate_code()` |
| `OrganisationInviteQuerySet` | Status-based filtering | `.active()`, `.expired()`, `.used()` |

> **Important:** `Organisation.owner` is a FK to `Collaborator`, **not** to `User`.
> Deleting the owner `Collaborator` instance cascades to the entire organisation.

## API Endpoints

| Method | URL | Auth | Permission | Rate Limit | Description |
|--------|-----|------|------------|------------|-------------|
| `GET` | `/api/organisations/` | Required | `IsAdminUser` | — | List organisations |
| `POST` | `/api/organisations/` | Required | `IsOrganisationCreator` | — | Create an organisation |
| `GET` | `/api/organisations/<id>/` | Required | Staff or collaborator | — | Retrieve organisation details |
| `PUT/PATCH` | `/api/organisations/<id>/` | Required | `IsOrganisationOwner` | — | Update organisation |
| `GET` | `/api/organisations/<id>/collaborators/` | Required | Collaborator on org | — | List collaborators |
| `POST` | `/api/organisations/<id>/collaborators/add/` | Required | `IsOrganisationOwner` | — | Invite a user by email |
| `PATCH` | `/api/organisations/<id>/collaborators/<id>/job-title/` | Required | Owner or member | — | Update job title |
| `POST` | `/api/organisations/<id>/transfer-ownership/` | Required | `IsOrganisationOwner` | — | Transfer ownership |
| `DELETE` | `/api/organisations/collaborators/<id>/` | Required | `IsOrganisationOwner` | — | Remove collaborator |
| `GET` | `/api/organisations/<id>/invites/` | Required | `IsOrganisationOwner` | — | List invites (optional `?status=active\|expired\|used`) |
| `POST` | `/api/organisations/<id>/invites/` | Required | `IsOrganisationOwner` | 10/hr | Create invite code |
| `DELETE` | `/api/organisations/<id>/invites/<invite_id>/` | Required | `IsOrganisationOwner` | — | Revoke unused invite |
| `POST` | `/api/organisations/join/` | Required | Collaborator | 20/hr | Join via invite code |

## Permissions & Roles

- **`IsOrganisationCreator`** — staff or collaborator without an existing organisation.
- **`IsOrganisationOwner`** — authenticated user must be the OWNER collaborator of the target org.
- **`IsAuthenticatedCollaborator`** — read access for any collaborator on the org.
- **Feature gate:** `max_collaborators` from `COLLABORATOR_FEATURES` blocks adding
  more members than the plan allows.

## Key Workflows

1. **Organisation creation** — `POST /api/organisations/`; an OWNER `Collaborator` is
   created automatically and assigned as `Organisation.owner`.
2. **Invite issuance** — Owner creates a code with an optional `expires_in_hours`
   (1–168 h, default 72 h); code uses `secrets.choice()` over a 33-char alphabet.
3. **Invite redemption** — Collaborator calls `POST /join/` with the code; the view
   uses `select_for_update()` to prevent concurrent double-redemption race conditions.
4. **Ownership transfer** — Owner calls `POST /transfer-ownership/` pointing to
   another collaborator's UUID.

## Dependencies

**Requires:** `users` (User), `payments` (SubscriptionPlan, Subscription for
entitlement checks)

**Used by:** `follows` (Collaborator FK), `messaging` (Thread collaborator FK),
`contracts` (Contract organisation FK), `core` (permission helpers)
