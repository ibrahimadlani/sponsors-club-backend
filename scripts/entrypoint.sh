#!/bin/sh

# Exit immediately if a command exits with a non-zero status to surface
# boot issues early in container logs.
set -e

# Resolve the port exposed by the platform (defaults to 8000 for local usage).
APP_PORT="${PORT:-8000}"

# Always operate from the Django project root.
cd /app/

# Launch Gunicorn with a shared memory worker tmp directory to improve
# performance on Alpine-based images.
exec /py/bin/gunicorn \
    --worker-tmp-dir /dev/shm \
    --bind "0.0.0.0:${APP_PORT}" \
    core.wsgi:application
