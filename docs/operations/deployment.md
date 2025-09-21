# Deployment runbook

This guide explains how the production container is built, which scripts it exposes,
and the environment variables you need to provide when running the backend.

## Container image layout
- **Base image:** `python:3.11.5-alpine3.18` keeps the runtime lean while providing
  musl-based security patches.
- **Virtual environment:** the Dockerfile creates an isolated environment in `/py`,
  upgrades `pip`, and installs the dependencies listed in `requirements.txt`.
- **System packages:** Alpine packages for PostgreSQL (`postgresql-client` and
  build headers) are installed temporarily to compile database drivers.
- **Non-root user:** the image adds a dedicated `django-user` account and switches
  to it for runtime safety.
- **Entrypoint scripts:** `scripts/entrypoint.sh` (Gunicorn) and
  `scripts/migrate.sh` (schema migrations) are copied in and marked executable.

> The resulting image exposes port `8000` and sets `PATH` so that `/py/bin` takes
> precedence, meaning all `python`, `pip`, and `gunicorn` invocations use the
> virtual environment by default.

## Runtime configuration
Provide these variables when deploying:

| Variable | Purpose | Default |
| --- | --- | --- |
| `PORT` | Port Gunicorn binds to. | `8000` |
| `DJANGO_SETTINGS_MODULE` | Override Django settings if needed. | `core.settings` |
| `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | Optional credentials
  to create/update an admin user during migrations. | unset |
| `DRF_YASG_ENABLED` | Set to `true` to serve `/api/docs/` and `/api/redoc/`. | `False` |

Provide a hardened `SECRET_KEY`, disable `DEBUG`, and configure the production
database through a custom settings module or environment-specific override.
`DJANGO_SETTINGS_MODULE` lets you point the container to that module.

## Startup sequence
1. **Run migrations:** execute `scripts/migrate.sh` inside a one-off container or
   release job. The script:
   - generates missing migrations (`manage.py makemigrations`),
   - applies them with `manage.py migrate --noinput`,
   - optionally provisions a superuser when `DJANGO_SUPERUSER_*` are set.
2. **Launch the web process:** `scripts/entrypoint.sh` changes to `/app/` and
   starts Gunicorn with `core.wsgi:application` on `0.0.0.0:${PORT}` using
   `/dev/shm` as the worker tmp directory for Alpine compatibility.
3. **Scale workers:** adjust Gunicorn settings via container arguments or a
   process manager (e.g. add `--workers` and `--timeout` flags) when running the
   entrypoint.

### Static files
`collectstatic` is commented inside `scripts/migrate.sh`. Uncomment the command
when your deployment requires Django to gather static assets (e.g. if serving via
Whitenoise or an object storage bucket).

## Release checklist
- Build and push the Docker image with the latest commit.
- Run `scripts/migrate.sh` against the production database.
- Restart the application process so the new Gunicorn instance loads the updated
  code.
- Monitor logs for migration output and Gunicorn startup messages to confirm a
  healthy deployment.

Running `python manage.py check --deploy` before releasing is recommended to
surface missing security settings early.
