# Athletes domain

## Overview

The `athletes` app stores athlete profiles under a **"Sport-Business"** valuation
model: an athlete's commercial value is computed from verified sporting achievements
and real physical audience exposure — not follower counts alone. It also manages
sport taxonomy, sponsorship inventory, and entourage mandates with legal compliance
rules for French sports agency law.

## Data model

### Sport taxonomy

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Sport` | High-level sport category | `name`, `slug`, `emoji`, `category` (TEAM / INDIVIDUAL / MIXED) |
| `SportDiscipline` | Specific event within a sport (e.g. "100m haies") | `sport`, `name`, `slug`, `is_olympic` |
| `AthleteDiscipline` | Through table: athlete ↔ discipline | `athlete`, `discipline`; `clean()` validates discipline belongs to athlete's sport |

### Athlete profile

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Athlete` | Core profile managed by an agent | `sport`, `agent`, `full_name`, `birth_date`, `nationality`, `club_name`, `federation_name`, `license_number`; `total_physical_reach` (property), `sponsorship_tier` (property) |
| `AthletePhoto` | Gallery images for the public profile | `athlete`, `image`, `caption`, `position` |

### Commercial valuation

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `SportingAchievement` | Verified competition result | `title`, `date`, `level` (LOCAL / REGIONAL / NATIONAL / INTERNATIONAL), `ranking`, `proof_url`, `verification_status` (PENDING / VERIFIED / REJECTED); only VERIFIED achievements count for `sponsorship_tier` |
| `UpcomingEvent` | Future event with physical audience | `event_name`, `start_date`, `end_date`, `location`, `estimated_physical_audience`, `target_demographic`, `is_broadcasted`; summed by `total_physical_reach` |
| `SponsorshipAsset` | Advertisement space the athlete sells | `asset_type` (PHYSICAL_GEAR / DIGITAL_SHOUTOUT / EVENT_PRESENCE / IMAGE_RIGHTS), `name`, `description`, `estimated_value_min`, `estimated_value_max`, `is_available` |

### Entourage mandates

`RepresentationMandate` is the through model for the `Athlete.entourage` M2M
relation (via `RepresentativeProfile`). It encodes *what* a person is allowed to
do on behalf of an athlete.

**Fields:**

| Field | Description |
|-------|-------------|
| `role` | PARENT_GUARDIAN / COACH / CLUB_OFFICIAL / LICENSED_AGENT / MANAGER |
| `can_manage_messaging` | May communicate with sponsors |
| `can_negotiate_contracts` | May open/edit contract clauses |
| `can_sign_legally` | May sign contracts with legal effect |
| `commission_percentage` | 0–20 %; must be 0 for non-licensed roles |
| `is_active` | Soft-delete flag; inactive mandates are ignored by permission checks |
| `proof_document` | Uploaded mandate document (required for LICENSED_AGENT) |
| `verified` | Staff-verified flag; required before the mandate gates DocuSign signing |
| `valid_from` / `valid_until` | Optional validity window |

**Legal constraints enforced in `clean()`:**

- **Rule 1 — Art. L222-5 Code du sport**: Representatives who are not
  `LICENSED_AGENT` cannot receive a commission (`commission_percentage > 0`).
- **Rule 2 — Minor athlete signing rights**: A `COACH` or `CLUB_OFFICIAL` cannot
  hold `can_sign_legally=True` for an athlete under 18. Only a `PARENT_GUARDIAN`
  may sign on behalf of a minor.

**`is_valid(check_date=None)` method:**

Returns `True` when the mandate can gate a DocuSign signing. Checks:
1. `is_active` must be True.
2. For `LICENSED_AGENT`: `proof_document` must be non-null and `verified` must be True.
3. Date window: if `valid_from` is set, today must be ≥ `valid_from`; if `valid_until`
   is set, today must be ≤ `valid_until`.

## Computed properties on `Athlete`

| Property | Logic |
|----------|-------|
| `sponsorship_tier` | Returns `"Élite Nationale"` (NATIONAL or INTERNATIONAL verified achievement), `"Espoir Régional"` (REGIONAL), or `"Héros Local"` (LOCAL or none). Only VERIFIED achievements count. |
| `total_physical_reach` | Sum of `estimated_physical_audience` for all future `UpcomingEvent` records (today or later). |

Both properties exploit the prefetch cache (`_prefetched_objects_cache`) when
available, avoiding N+1 queries in list views.

## API endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/athletes/` | Required | `IsCollaboratorUser` | List athletes visible to collaborators |
| `POST` | `/api/athletes/` | Required | `IsAgentUser` | Create athlete (plan quota enforced) |
| `GET` | `/api/athletes/<id>/` | Required | `CanViewAthlete` | Retrieve single athlete |
| `PUT/PATCH` | `/api/athletes/<id>/` | Required | `IsAthleteOwner` | Update athlete (owning agent only) |
| `DELETE` | `/api/athletes/<id>/` | Required | `IsAthleteOwner` | Delete athlete |
| `GET` | `/api/athletes/slug/<slug>/` | Required | `CanViewAthlete` | Retrieve athlete by slug |
| `GET` | `/api/athletes/<id>/photos/` | Required | `CanViewAthlete` | List athlete gallery photos |
| `GET` | `/api/me/athletes/` | Required | `IsAgentUser` | List authenticated agent's athletes |
| `GET` | `/api/sports/` | Public | — | List all sports |
| `GET` | `/api/sports/<uuid>/disciplines/` | Public | — | List disciplines for a sport |

## Permissions & roles

- **`IsAgentUser`** — user must have `account_type=AGENT` and a linked `AgentProfile`.
- **`IsCollaboratorUser`** — user must have `account_type=COLLABORATOR`.
- **`CanViewAthlete`** — the owning agent, any collaborator, or staff.
- **`IsAthleteOwner`** — only the agent who created the athlete.
- **`athlete_slots` feature gate** — checked via `AGENT_FEATURES` matrix; creation
  is blocked when `max_athletes` quota is reached.

## Key workflows

1. **Athlete creation** — Agent POSTs to `/api/athletes/`; serializer checks `max_athletes`
   quota, creates the profile, and auto-generates a URL slug.
2. **Mandate granting** — `RepresentationMandate` is created (via admin or dedicated
   API) linking a `RepresentativeProfile` to the athlete with the desired role and
   permissions.
3. **Sponsorship tier computation** — The agent uploads `SportingAchievement` records
   with `proof_url`; staff sets `verification_status=VERIFIED`. The `sponsorship_tier`
   property then reflects the highest verified level.
4. **Signing gate** — Before DocuSign envelope creation, `contracts.views` calls
   `RepresentationMandate.is_valid()` for the agent's mandate. A mandate without
   `proof_document` or `verified=True` will block signing with a 403.

## Dependencies

**Requires:** `users` (AgentProfile, RepresentativeProfile), `payments` (max_athletes
entitlement via subscription plan)

**Used by:** `follows`, `messaging`, `contracts`, `analytics`, `payments`
