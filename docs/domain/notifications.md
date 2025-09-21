# Notifications domain

## Overview
The notifications app stores user-targeted alerts (messages, contract updates,
follow activity, payment events) and serves paginated feeds and read-state
updates. Access is governed by the `notification_center` feature entitlement.

## Data model
- **`Notification`** links to a `User`, records a typed category (e.g.
  `NEW_MESSAGE`, `CONTRACT_STATUS`), stores a JSON `payload`, and tracks whether
  the entry has been read. Indexes support filtering by user, read state, and
  newest-first ordering.

## Serializers
- `NotificationSerializer` exposes the read-only fields returned to clients.
- `NotificationReadSerializer` accepts `is_read` updates for toggling state.

## Permissions and entitlements
Both endpoints require authentication. Before listing or updating notifications,
`NotificationListView` and `NotificationReadView` call
`user_feature_requirement("notification_center")` and return the structured
payload from `requirement_denied_payload()` when the feature is unavailable.

## API surface
Routes are mounted under `/api/notifications/`.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/notifications/` | Paginated list of notifications for the current user with optional `?is_read=true|false`. | Authenticated with notification feature |
| `PATCH` | `/notifications/<notification_id>/read/` | Toggle the read flag on a notification. | Authenticated with notification feature |

Pagination defaults to 25 items per page (max 100) via `NotificationPagination`.
