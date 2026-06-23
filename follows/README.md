# `follows/` — Collaborator-to-athlete follow relationships with notification preferences.

## Responsibility

- Let organisation collaborators track specific athletes and receive targeted alerts.
- Enforce per-plan follow quota (`max_follows` feature gate).
- Store per-follow notification preferences (news, stats, contracts).

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Follow` | Collaborator follows an athlete | `collaborator` (FK), `athlete` (FK), `notify_news`, `notify_stats`, `notify_contracts`; unique_together `(collaborator, athlete)` |

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `POST` | `/api/athletes/<uuid>/follow/` | Required | `IsCollaboratorUser` | Follow an athlete (plan quota checked) |
| `DELETE` | `/api/athletes/<uuid>/follow/` | Required | `IsCollaboratorUser` | Unfollow an athlete |
| `GET` | `/api/me/follows/` | Required | `IsCollaboratorUser` | List the authenticated collaborator's followed athletes |

## Permissions & Roles

- **`IsCollaboratorUser`** — only collaborator-type accounts can follow athletes.
- **`max_follows` gate** — `COLLABORATOR_FEATURES["follow_athletes"]` enforces a
  numeric limit. Attempting to follow beyond the plan limit returns a structured
  denial payload.

## Key Workflows

1. **Follow** — `POST /api/athletes/<uuid>/follow/`; quota is checked against the
   active subscription; a `Follow` record is created with default notification prefs.
2. **Unfollow** — `DELETE` on the same URL; the `Follow` record is deleted.
3. **List follows** — `GET /me/follows/` returns the collaborator's athlete watchlist
   with notification settings.

## Dependencies

**Requires:** `athletes` (Athlete), `organisations` (Collaborator), `core` (feature
gates)

**Used by:** `notifications` (NEW_FOLLOW notification type)
