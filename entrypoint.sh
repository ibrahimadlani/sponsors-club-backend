#!/bin/sh
set -e

APP_PORT="${PORT:-8000}"

cd /app/

exec /py/bin/gunicorn \
    --worker-tmp-dir /dev/shm \
    --bind "0.0.0.0:${APP_PORT}" \
    core.wsgi:application
