# `athletes/` — Athlete profiles, sport taxonomy, sponsorship inventory, and entourage mandates.

## Responsibility

- Manage athlete profiles using a **"Sport-Business"** valuation model: commercial
  value is computed from verified sporting achievements and physical audience reach,
  not follower counts alone.
- Sport taxonomy (Sport → SportDiscipline hierarchy).
- Sponsorship inventory (the advertisement spaces an athlete sells).
- Representation mandates with legal compliance rules for French sports agency law.

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Sport` | High-level sport category | `name`, `slug`, `emoji`, `category` (TEAM / INDIVIDUAL / MIXED) |
| `SportDiscipline` | Specific event within a sport | `sport`, `name`, `slug`, `is_olympic` |
| `AthleteDiscipline` | Through table: athlete ↔ discipline | `athlete`, `discipline`; `clean()` validates discipline belongs to athlete's sport |
| `Athlete` | Core athlete profile | `sport`, `agent`, `full_name`, `birth_date`, `nationality`, `club_name`; `total_physical_reach` property, `sponsorship_tier` property |
| `AthletePhoto` | Gallery images | `image`, `caption`, `position` |
| `SportingAchievement` | Verified competition result | `title`, `level`, `verification_status` (PENDING / VERIFIED / REJECTED), `proof_url`; drives `sponsorship_tier` |
| `UpcomingEvent` | Future event with physical audience | `estimated_physical_audience`; drives `total_physical_reach` |
| `SponsorshipAsset` | Advertisement space for sale | `asset_type`, `estimated_value_min/max`, `is_available` |
| `RepresentationMandate` | Entourage permission grant | `role`, `can_sign_legally`, `commission_percentage`, `proof_document`, `verified`, `valid_from/until`; `is_valid()`, `clean()` |

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/athletes/` | Required | `IsCollaboratorUser` | List athletes (collaborator view) |
| `POST` | `/api/athletes/` | Required | `IsAgentUser` | Create athlete (plan quota enforced) |
| `GET` | `/api/athletes/<id>/` | Required | `CanViewAthlete` | Retrieve single athlete |
| `PUT/PATCH` | `/api/athletes/<id>/` | Required | `IsAthleteOwner` | Update athlete |
| `DELETE` | `/api/athletes/<id>/` | Required | `IsAthleteOwner` | Delete athlete |
| `GET` | `/api/athletes/slug/<slug>/` | Required | `CanViewAthlete` | Retrieve athlete by URL slug |
| `GET` | `/api/athletes/<id>/photos/` | Required | `CanViewAthlete` | List athlete gallery photos |
| `GET` | `/api/me/athletes/` | Required | `IsAgentUser` | List authenticated agent's athletes |
| `GET` | `/api/sports/` | Public | — | List all sports |
| `GET` | `/api/sports/<uuid>/disciplines/` | Public | — | List disciplines for a sport |

## Permissions & Roles

- **`IsAgentUser`** — `account_type=AGENT` + `AgentProfile` exists.
- **`IsCollaboratorUser`** — `account_type=COLLABORATOR`.
- **`CanViewAthlete`** — owning agent, any collaborator, or staff.
- **`IsAthleteOwner`** — only the creating agent.
- **`athlete_slots` gate** — `AGENT_FEATURES["athlete_slots"]` blocks creation when
  `max_athletes` quota is reached.

## Key Workflows

1. **Athlete creation** — Agent creates athlete; slug is auto-generated; plan quota
   is checked against `max_athletes`.
2. **Mandate granting** — `RepresentationMandate` links a `RepresentativeProfile` to
   an athlete. `clean()` enforces legal rules (no commission for non-licensed roles;
   no signing rights for coaches/club officials over minors).
3. **Sponsorship tier** — Agent adds `SportingAchievement` records; staff sets
   `verification_status=VERIFIED`. The `sponsorship_tier` property returns `"Élite
   Nationale"`, `"Espoir Régional"`, or `"Héros Local"` based on the highest verified level.
4. **Signing gate** — `contracts.views._has_valid_mandate()` calls
   `RepresentationMandate.is_valid()`. A mandate must be `verified=True` with a valid
   `proof_document` and within its `valid_from/valid_until` window to pass.

## Dependencies

**Requires:** `users` (AgentProfile, RepresentativeProfile), `payments` (max_athletes
entitlement via active SubscriptionPlan)

**Used by:** `follows`, `messaging`, `contracts` (RepresentationMandate), `analytics`
