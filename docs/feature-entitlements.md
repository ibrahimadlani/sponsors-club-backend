# Feature entitlement reference

This annex complements the [feature entitlement architecture guide](architecture/feature-entitlements.md)
with concrete payloads returned by the API when a plan check fails and examples of
the `/users/me/entitlements/` discovery endpoint.

## Denied response contract
Whenever a feature check blocks an action, the API responds with HTTP 403 and the
following JSON envelope:

| Field | Description |
| --- | --- |
| `detail` | Human-readable explanation that can be surfaced in the UI. |
| `required_feature` | Feature flag key evaluated by the backend. |
| `allowed_values` | Optional list of accepted values for the entitlement. |
| `upgrade_url` | Link to the billing or upgrade page clients should open. |
| `recommended_plans` | Friendly plan names to promote in upgrade messaging. |

### Sample payload
```json
{
  "detail": "Messaging upgrade required: switch to Agent Pro+ (messaging_tier=pro_plus) to open new conversations.",
  "required_feature": "messaging_tier",
  "allowed_values": ["pro_plus", "enterprise"],
  "upgrade_url": "https://app.sponsorsclub.com/plans/agent",
  "recommended_plans": ["Agent Pro+", "Agent Enterprise"]
}
```

## Agent features
| Code | Label | Required feature | Recommended plans | Notes |
| ---- | ----- | ---------------- | ----------------- | ----- |
| `messaging_initiate` | Messaging (initiate threads) | `messaging_tier` ∈ {`pro_plus`, `enterprise`} | Agent Pro+, Agent Enterprise | Required to open new DM threads. Replying to existing threads stays open to all participants. |
| `subscription_management` | Manage agent subscription | `agent_subscription_management` truthy | Agent Pro+, Agent Enterprise | Grants access to manage billing from the agent dashboard. |

## Organisation collaborator features
| Code | Label | Required feature | Recommended plans | Notes |
| ---- | ----- | ---------------- | ----------------- | ----- |
| `athlete_stats_all` | Athlete statistics (all) | `athlete_stats_scope` = `all` | Organisation Pro, Organisation Enterprise | Unlocks platform-wide athlete analytics for collaborators. |
| `collaborator_invites` | Invite collaborators | `collaborator_invites` truthy | Organisation Pro, Organisation Enterprise | Allows owners to add teammates. |

### Sample payload
```json
{
  "detail": "Requires organisation subscription with athlete_stats_scope=all (Organisation Pro or higher) to unlock athlete insights.",
  "required_feature": "athlete_stats_scope",
  "allowed_values": ["all"],
  "upgrade_url": "https://app.sponsorsclub.com/plans/organisation",
  "recommended_plans": ["Organisation Pro", "Organisation Enterprise"]
}
```

## Discovering current entitlements
Use `GET /api/users/me/entitlements/` to obtain the account type and the status of
each feature. Clients can render upgrade banners directly from the payload.

```http
GET /api/users/me/entitlements/
Authorization: Bearer <token>
```

```json
{
  "account_type": "AGENT",
  "features": [
    {
      "code": "messaging_initiate",
      "label": "Messaging (initiate threads)",
      "description": "Allows an agent to initiate new messaging threads with collaborators.",
      "granted": true,
      "required_feature": "messaging_tier",
      "allowed_values": ["pro_plus", "enterprise"],
      "upgrade_url": "https://app.sponsorsclub.com/plans/agent",
      "recommended_plans": ["Agent Pro+", "Agent Enterprise"]
    }
  ]
}
```

Integrate this endpoint into the onboarding flow or settings pages to pre-empt 403
responses with proactive upgrade messaging.
