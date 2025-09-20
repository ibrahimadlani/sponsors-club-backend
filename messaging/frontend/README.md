# Messaging React Playground

A lightweight React application that lives alongside the Django messaging app. It offers a quick way to experiment with the REST and WebSocket features implemented for collaborator/agent chat threads.

## Features

- Configure the API base URL and paste a SimpleJWT access token directly in the UI.
- Automatically lists the threads that belong to the authenticated collaborator or agent.
- Displays the latest messages in the selected thread and keeps the list fresh through WebSocket pushes.
- Allows sending text messages via WebSocket with automatic REST fallback, and uploading attachments through the REST API.
- Marks inbound messages as read immediately using the `/api/messages/{id}/read/` endpoint.

## Getting started

```bash
cd messaging/frontend
npm install
npm run dev
```

The Vite dev server runs on [http://localhost:5173](http://localhost:5173) by default. Make sure your Django backend is also running (e.g. `python manage.py runserver 0.0.0.0:8000`).

In the playground UI:

1. Enter the backend base URL (for instance `http://localhost:8000`).
2. Paste a valid SimpleJWT access token in the token field.
3. Click **Load threads** to fetch your conversations.
4. Select a thread to view existing messages, send new ones, and observe WebSocket activity in real time.

## WebSocket authentication

Browsers cannot set custom `Authorization` headers during the WebSocket handshake. The playground therefore appends the JWT as a `token` query parameter. The backend middleware accepts this parameter and authenticates the user before allowing them to join the thread group.

## Production notes

- The project intentionally keeps dependencies light: Vite for development, plus React 18.
- This directory is self-contained and optional; it does not affect the Django application unless you start the dev server manually.
- Feel free to adjust styling or extend components as needed for manual QA.
