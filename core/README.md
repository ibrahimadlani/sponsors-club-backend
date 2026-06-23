# `core/` — Global configuration, URL routing, and the feature entitlement engine.

## Responsibility

- Django project settings, ASGI/WSGI entry points, and URL routing.
- Feature entitlement matrix that maps subscription plan features to per-action
  permission checks across all domain apps.
- Shared permission helpers used by every app (`permissions.py`).
- Email delivery via AWS SES (`emails.py`).
- Custom authentication backend (`auth.py`).

## Models

No models. `core` is a configuration-only app.

## API Endpoints

No endpoints. `core` acts as the URL routing hub (`core/urls.py`) that mounts
all domain apps under `/api/`.

Routes mounted: `/api/users/`, `/api/organisations/`, `/api/athletes/`,
`/api/sports/`, `/api/me/`, `/api/follows/`, `/api/messaging/`,
`/api/notifications/`, `/api/contracts/`, `/api/clause-templates/`,
`/api/analytics/`, `/api/payments/`, `/api/docs/`, `/api/redoc/`, `/api/schema/`.

## Feature entitlement engine (`core/feature_matrix.py`)

Two feature dictionaries define per-action requirements for each account type:

```python
AGENT_FEATURES = {
    "athlete_slots": {...},      # max_athletes quota
    "messaging_initiate": {...}, # send first message
    "contract_management": {...},
    ...
}

COLLABORATOR_FEATURES = {
    "organisation_subscription_management": {...},
    "contract_management": {...},
    "follow_athletes": {...},
    ...
}

FEATURE_MATRIX = {
    "agent": AGENT_FEATURES,
    "collaborator": COLLABORATOR_FEATURES,
}
```

The entitlement engine works in three steps:

1. **Load plan features** — `get_agent_plan_features(user)` or
   `get_collaborator_plan_features(user)` reads the active `Subscription.plan.features`
   JSON, falling back to a free-tier default.
2. **Check requirement** — `user_feature_requirement(feature_key)` compares the
   user's plan features against `FEATURE_MATRIX` to determine if access is allowed.
3. **Return denial** — When access is blocked, `requirement_denied_payload()` returns
   a structured JSON payload the client uses to surface an upgrade CTA.

## Permissions (`core/permissions.py`)

Key helpers (25+ functions):

| Helper | Used by |
|--------|---------|
| `IsAgentUser` | `athletes/`, `contracts/` |
| `IsCollaboratorUser` | `athletes/`, `follows/` |
| `IsOrganisationOwner` | `organisations/` |
| `IsOrganisationCreator` | `organisations/` |
| `IsAuthenticatedCollaborator` | `organisations/` |
| `CanViewAthlete` | `athletes/` |
| `IsAthleteOwner` | `athletes/` |
| `IsAgentOrStaff` | `analytics/` |
| `collaborator_meets_requirement()` | `contracts/`, `organisations/` |
| `requirement_denied_payload()` | all apps |

## Key Workflows

1. **Feature gate check** — `collaborator_meets_requirement(request, "contract_management")`
   returns `(allowed: bool, denial_payload: dict)`. Views call this at the top of
   each protected action.
2. **Plan feature loading** — Features are resolved lazily from the user's active
   subscription. Staff users bypass all feature gates.

## Dependencies

**Requires:** `payments` (Subscription, SubscriptionPlan), `organisations`
(Collaborator), `users` (User, AgentProfile)

**Used by:** all domain apps import from `core.permissions` and `core.feature_matrix`
