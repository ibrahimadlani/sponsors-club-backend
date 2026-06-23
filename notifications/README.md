# `notifications/` — User-targeted alerts with real-time WebSocket delivery.

## Responsibility

- Persist user-facing notifications for all domain events (messages, contract updates,
  follows, stat changes, payments).
- Serve a paginated notification feed with read/unread filtering.
- Push new notifications to connected clients via Django Channels.

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Notification` | Single user notification | `user` (FK), `type` (NEW_MESSAGE / CONTRACT_STATUS / NEW_FOLLOW / STAT_UPDATE / PAYMENT), `payload` (JSON), `is_read`; ordered by `-created_at` |

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/notifications/` | Required | `IsAuthenticated` | Paginated notification feed (filterable by `?is_read=true/false`) |
| `PATCH` | `/api/notifications/<uuid>/read/` | Required | Notification owner | Mark a single notification as read |

> **WebSocket:** `ws/notifications/` — real-time push for new notifications to
> authenticated connected users (Django Channels consumer).

## Permissions & Roles

- **`IsAuthenticated`** — required on all endpoints.
- **Notification owner** — users can only read or acknowledge their own notifications.
- **`notification_center` gate** — the notification feed may require a plan feature;
  entitlement is checked at list time via `COLLABORATOR_FEATURES`.

## Key Workflows

1. **Notification emission** — Domain apps (messaging, contracts, follows) create a
   `Notification` record for the target user. The Channels consumer broadcasts it
   immediately to any connected session.
2. **Feed consumption** — `GET /notifications/` returns unread notifications first
   (ordered by `-created_at`). The client can filter with `?is_read=false`.
3. **Acknowledge** — `PATCH /notifications/<uuid>/read/` sets `is_read=True`.

## Dependencies

**Requires:** `users` (User FK)

**Used by:** `messaging` (NEW_MESSAGE), `contracts` (CONTRACT_STATUS), `follows`
(NEW_FOLLOW), `analytics` (STAT_UPDATE), `payments` (PAYMENT)
