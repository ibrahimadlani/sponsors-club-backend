# Proof-of-concept templates

The repository ships two HTML playgrounds under `templates/poc/` to help product
teams and QA exercise JWT authentication and the messaging API without writing
front-end code.

## Authentication sandbox (`/poc/login/`)
- Provides forms to call `POST /api/users/login/`, `POST /api/users/login/refresh/`
  and `GET /api/users/me/`.
- Stores access and refresh tokens in `localStorage` so subsequent requests reuse
  them. Buttons let you copy, refresh, or clear the tokens.
- Automatically adds CSRF headers for unsafe HTTP methods when cookies are
  present, matching the behaviour expected by DRF.
- Useful for generating credentials that can then be pasted into Swagger (`/api/docs/`)
  or the messaging tester below.

### Usage
1. Visit `/poc/login/` in a browser with the Django server running.
2. Submit a known user email/password. Successful responses display the JSON
   payload returned by the API.
3. Use the **Interroger /me** button to confirm the token works and inspect role
   assignments or entitlements returned by `/api/users/me/`.
4. Copy the access token when you need to authenticate other tools.

## Messaging tester (`/poc/messaging/`)
- React single-page helper that talks to `/api/messaging/threads/`,
  `/api/messaging/threads/<id>/messages/`, and `/api/messaging/messages/<id>/read/`.
- Lets you list threads, paginate through messages, send replies, toggle read
  state, and create new conversations by specifying collaborator/agent IDs.
- Persists the API base URL and JWT token locally so refreshes keep your
  configuration.
- Keeps a rolling log of the last 25 API calls for debugging.

### Usage
1. Retrieve a valid JWT (e.g. via `/poc/login/`) and navigate to `/poc/messaging/`.
2. Paste the messaging API base URL (defaults to `http://localhost:8000/api/messaging`).
3. Paste the JWT into the token field and click **Rafraîchir les conversations** to
   load the first page of threads.
4. Select a thread to fetch messages, post replies, or mark items as read. Use the
   **Créer la conversation** form to open a new thread when you know the relevant
   UUIDs.

## Troubleshooting tips
- Both pages rely on the browser storing tokens; clear `localStorage` if you need
  to reset the state.
- Messaging endpoints require the authenticated user to hold the correct feature
  entitlements. A `403` response with an upgrade payload means the plan must be
  adjusted (see [Feature entitlements](../feature-entitlements.md)).
- When testing against a non-localhost host, ensure CORS, CSRF, and HTTPS
  settings in `core/settings.py` allow your origin.
