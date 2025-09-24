# Athletes domain

## Overview
The athletes app stores athlete profiles, sports catalogues, and the agent-side
APIs used to manage rosters. It enforces per-plan limits when creating athletes
and restricts operations to the owning agent or invited collaborators.

## Data model
- **`Sport`** captures the sport name and discipline, referenced by athletes.
- **`Athlete`** links to a `Sport` and an owning `AgentProfile`. It stores core
  biography fields, cached social metrics (`followers_count_cached` and
  `engagement_rate_cached`), social links, and optional avatar uploads.

## Serializers
- `AthletePublicSerializer` exposes the readonly fields returned in nested
  contexts such as follows, messaging, and analytics.
- `AthleteSerializer` is the write-capable serializer used by the management
  endpoints. It validates the requesting user has an `AgentProfile`, blocks agent
  reassignment on updates, and enforces feature limits:
  - `get_agent_plan_features()` retrieves the current subscription allowances.
  - `user_feature_requirement("athlete_slots")` pairs with the
    `AGENT_FEATURES` matrix to build entitlement denial payloads via
    `requirement_denied_payload()`.
  - If the plan provides a numeric `max_athletes`, the serializer counts current
    athletes for the agent and raises `PermissionDenied` once the threshold is
    reached.

## Permissions
Action-specific guards in `AthleteViewSet` ensure that:

- Listing (`GET /api/athletes/`) requires an authenticated collaborator account
  via `IsCollaboratorUser`.
- Retrieving (`GET /api/athletes/<id>/`) is allowed for the owning agent,
  collaborators, or staff through `CanViewAthlete`.
- Creating requires the requester to be an authenticated agent with a profile
  (`IsAgentUser`) and enough feature slots as described above.
- Updating and deleting are limited to the owning agent via `IsAthleteOwner`.

The `MyAthletesView` endpoint additionally filters by the authenticated agent's
profile, while `SportListView` is public.

## API surface
Routes are mounted under `/api/` by the DRF router:

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/athletes/` | List athletes visible to collaborator accounts. | Authenticated collaborator |
| `POST` | `/athletes/` | Create a new athlete subject to plan limits. | Authenticated agent |
| `GET` | `/athletes/<id>/` | Retrieve a single athlete. | Authenticated agent/collaborator/staff |
| `PUT/PATCH` | `/athletes/<id>/` | Update athlete details (owner only). | Owning agent |
| `DELETE` | `/athletes/<id>/` | Remove an athlete (owner only). | Owning agent |
| `GET` | `/me/athletes/` | List athletes owned by the current agent. | Authenticated agent |
| `GET` | `/sports/` | Enumerate configured sports. | Public |

All list responses use DRF's default pagination settings inherited from the
project.
