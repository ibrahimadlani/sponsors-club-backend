# Feature Entitlements & Upgrade Messaging

This API enforces feature flags by account type. Whenever access is denied the
response body includes:

- `detail`: branded explanation of the missing capability and required plan
- `required_feature`: the plan feature key our backend checks
- `allowed_values`: optional whitelist of acceptable values
- `upgrade_url`: deep link to the billing page for upgrades
- `recommended_plans`: friendly plan names to pitch in-app

## Agent Features

| Code | Label | Required Feature | Recommended Plans | Notes |
| ---- | ----- | ---------------- | ----------------- | ----- |
| `messaging_initiate` | Messaging (initiate threads) | `messaging_tier` ∈ {`pro_plus`, `enterprise`} | Agent Pro+, Agent Enterprise | Required to open new DM threads. Replying to existing threads stays open to all participants. |
| `subscription_management` | Manage agent subscription | `agent_subscription_management` | Agent Pro+, Agent Enterprise | Grants access to manage billing from the agent dashboard. |

### Sample denied payload

```json
{
  "detail": "Messaging upgrade required: switch to Agent Pro+ (messaging_tier=pro_plus) to open new conversations.",
  "required_feature": "messaging_tier",
  "allowed_values": ["pro_plus", "enterprise"],
  "upgrade_url": "https://app.sponsorsclub.com/plans/agent",
  "recommended_plans": ["Agent Pro+", "Agent Enterprise"]
}
```

## Organisation Collaborator Features

| Code | Label | Required Feature | Recommended Plans | Notes |
| ---- | ----- | ---------------- | ----------------- | ----- |
| `athlete_stats_all` | Athlete statistics (all) | `athlete_stats_scope` = `all` | Organisation Pro, Organisation Enterprise | Unlocks platform-wide athlete analytics for collaborators. |
| `collaborator_invites` | Invite collaborators | `collaborator_invites` truthy | Organisation Pro, Organisation Enterprise | Allows owners to add teammates. |

### Sample denied payload

```json
{
  "detail": "Requires organisation subscription with athlete_stats_scope=all (Organisation Pro or higher) to unlock athlete insights.",
  "required_feature": "athlete_stats_scope",
  "allowed_values": ["all"],
  "upgrade_url": "https://app.sponsorsclub.com/plans/organisation",
  "recommended_plans": ["Organisation Pro", "Organisation Enterprise"]
}
```

## Surfacing Entitlements

`GET /users/me/entitlements/` returns the current account type and the list of
features with `granted` status plus the metadata above so clients can render an
upgrade prompt inline.

```
GET /users/me/entitlements/
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

Use this endpoint to power upgrade modals or billing callouts in the product.
