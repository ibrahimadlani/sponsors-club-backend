# `messaging/` — Threaded inbox between organisation collaborators and athlete agents, with real-time WebSocket delivery.

## Responsibility

- Manage two-party conversation threads between a collaborator and an agent (optionally
  scoped to a specific athlete).
- Store and deliver individual messages with file attachment support.
- Track read/unread state per message.
- Push new messages to connected clients in real time via Django Channels.

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `Thread` | Two-way conversation | `collaborator` (FK), `agent` (FK), `athlete` (FK, optional), `last_message_at`; unique_together `(collaborator, agent, athlete)` |
| `Message` | Individual message in a thread | `thread` (FK), `sender` (FK User), `content`, `attachment` (FileField), `is_read` |

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/messaging/threads/` | Required | `IsAuthenticated` | List threads for the current user |
| `POST` | `/api/messaging/threads/` | Required | `messaging_initiate` gate | Create a new thread |
| `GET` | `/api/messaging/threads/<uuid>/messages/` | Required | Thread participant | List messages in thread |
| `POST` | `/api/messaging/threads/<uuid>/messages/` | Required | Thread participant | Send a message |
| `PATCH` | `/api/messaging/messages/<uuid>/read/` | Required | Message recipient | Mark a message as read |

> **WebSocket:** `ws/messaging/threads/<thread_id>/` — real-time message broadcast
> for connected thread participants (Django Channels consumer).

## Permissions & Roles

- **`IsAuthenticated`** — required on all endpoints.
- **Thread participant** — only the `collaborator` and `agent` linked to the thread
  may read or post messages (`IsThreadParticipant`).
- **`messaging_initiate` gate** — creating a new thread checks
  `AGENT_FEATURES["messaging_initiate"]` for agent-side creation and the equivalent
  collaborator feature for collaborator-side creation.

## Key Workflows

1. **Thread creation** — Collaborator or agent creates a thread; a unique constraint
   ensures one thread per (collaborator, agent, athlete) combination.
2. **Message send** — `POST /threads/<uuid>/messages/`; `last_message_at` is updated
   on the thread. The Channels consumer broadcasts the message to all connected
   participants.
3. **Read receipt** — `PATCH /messages/<uuid>/read/` sets `is_read=True`.

## Dependencies

**Requires:** `athletes` (Athlete FK), `organisations` (Collaborator FK), `users`
(User as sender), `core` (feature gates)

**Used by:** `notifications` (NEW_MESSAGE notification type)
