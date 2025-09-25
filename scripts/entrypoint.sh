#!/bin/sh

# Exit immediately if a command exits with a non-zero status to surface
# boot issues early in container logs.
set -e

# Resolve the port exposed by the platform (defaults to 8000 for local usage).
APP_PORT="${PORT:-8000}"

# Always operate from the Django project root.
cd /app/

# Launch Daphne so the container can serve both HTTP and WebSocket traffic.
exec /py/bin/daphne \
    --bind "0.0.0.0" \
    --port "${APP_PORT}" \
    core.asgi:application
