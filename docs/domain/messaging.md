# Messaging domain

## Overview
The messaging app provides a lightweight inbox between organisation
collaborators and agent profiles. It supports listing threads, creating new
conversations (optionally scoped to an athlete), posting messages, and toggling
read state while respecting entitlement rules for initiating contact.

## Data model
- **`Thread`** joins a `Collaborator`, `AgentProfile`, and optional `Athlete`. The
  unique constraint across these participants prevents duplicate threads, and the
  `last_message_at` timestamp drives ordering.
- **`Message`** stores the sender (any authenticated user in the thread), message
  content, optional attachment, and read flag.

## Serializers
- `ThreadSerializer` nests collaborator, agent, and athlete summaries for list
  responses. Creation is handled by `ThreadCreateSerializer`, which validates
  participant IDs, infers missing parties from the requesting user, and blocks
  duplicate threads.
- `MessageSerializer` serializes message records, while `MessageCreateSerializer`
  ensures a message contains text or an attachment and updates the thread's
  `last_message_at` timestamp.
- `MessageReadSerializer` toggles the `is_read` flag for recipients.

## Permissions and entitlements
- All thread and message endpoints require authentication. Object-level checks
  are provided by `IsThreadParticipant`, which ensures the user belongs to the
  thread before returning data or allowing updates.
- When an agent tries to create a thread, `ThreadViewSet.create()` verifies the
  `AGENT_FEATURES["messaging_initiate"]` requirement via
  `agent_meets_requirement()`. Failing the check returns the structured denial
  from `requirement_denied_payload()`.
- Collaborators must either be the authenticated user or staff when specifying a
  different collaborator ID; otherwise the request is forbidden.

## API surface
Routes are mounted under `/api/messaging/`.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/threads/` | Paginated threads for the current user ordered by `last_message_at`. | Authenticated |
| `POST` | `/threads/` | Create a new thread after entitlement checks. | Authenticated (agent must have messaging feature) |
| `GET` | `/threads/<thread_id>/messages/` | Paginated messages within a thread. | Thread participant |
| `POST` | `/threads/<thread_id>/messages/` | Post a message to the thread. | Thread participant |
| `PATCH` | `/messages/<message_id>/read/` | Toggle the read state (only allowed for the recipient). | Thread participant |

Pagination defaults: threads paginate at 20 per page (max 100) and messages at
50 per page (max 200).
