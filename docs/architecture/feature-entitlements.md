# Feature Entitlements Engine

The entitlement system enforces plan-based access across agents and organisation collaborators. It is defined centrally in `core.feature_matrix` and evaluated through helpers in `core.permissions`, so any API view can express feature requirements consistently.

## Canonical feature matrix

`FEATURE_MATRIX` stores two dictionaries: one for agent-facing features and one for collaborator-facing features. Each entry is a `FeatureRequirement` dataclass containing the plan feature key, optional allowed values, human copy for upgrade prompts, and suggested plans. For example:

- `messaging_initiate` requires agent plans where `messaging_tier` is `limited`, `pro_plus`, or `enterprise` so agents can open new conversations.
- `follow_slots` controls how many marketplace follows an organisation collaborator can create based on the `max_follows` quota exposed by their plan.

These records back both entitlement checks and the upgrade messaging returned to clients.

## Evaluating access

1. **Plan discovery** – `get_active_agent_subscription` and `get_active_organisation_subscriptions` fetch the latest active subscriptions, including related plan metadata.
2. **Feature extraction** – `_subscription_has_feature` inspects the JSON `features` column on the plan and supplements it with structured columns like `max_athletes` or `max_collaborators`.
3. **Fallback defaults** – When no subscription is active, `_load_plan_features` merges seeded defaults such as the `agent-free` or `org-starter` plans so development environments still return predictable entitlements.
4. **Requirement checks** – `agent_meets_requirement` and `collaborator_meets_requirement` compare the plan metadata with the `FeatureRequirement` definition.
5. **User-facing payload** – `feature_status_for_user` iterates through the matrix for the caller's account type, returning `code`, `label`, `description`, `granted`, `required_feature`, allowed values, upgrade links, and recommended plans.

## Denied responses

`requirement_denied_payload` packages a standardized error body when an entitlement is missing. Views can merge this payload into `PermissionDenied` responses to surface upgrade CTAs without duplicating copy. See `docs/feature-entitlements.md` for detailed examples that product teams can reuse in the UI.

## Integrating from views

To guard an endpoint:

1. Determine the relevant feature code (e.g. `messaging_initiate`).
2. Call `user_feature_requirement(request.user, feature_code)` to retrieve both the requirement metadata and the current grant status.
3. If not granted, raise a 403 with `requirement_denied_payload(requirement, default_detail)`.

Because these helpers live in `core.permissions`, they can be shared across apps like messaging, follows, contracts, and notifications without reimplementing subscription logic.
