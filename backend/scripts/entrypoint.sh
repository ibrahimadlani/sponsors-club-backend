#!/bin/sh

# Exit immediately if a command exits with a non-zero status to surface
# boot issues early in container logs.
set -e

# Resolve the port exposed by the platform (defaults to 8000 for local usage).
APP_PORT="${PORT:-8000}"

# Always operate from the Django project root.
cd /app/

# Ensure database migrations are applied before starting the application.
echo "Applying database migrations..."
/py/bin/python manage.py migrate --noinput

# Collect static assets so the container can serve them through the configured
# static files backend (e.g. WhiteNoise) or via an upstream proxy.
echo "Collecting static files..."
/py/bin/python manage.py collectstatic --noinput

# Launch Gunicorn with a shared memory worker tmp directory to improve
# performance on Alpine-based images.
exec /py/bin/gunicorn \
    --worker-tmp-dir /dev/shm \
    --bind "0.0.0.0:${APP_PORT}" \
    core.wsgi:application
