# Sponsors Club Backend

A Django REST API powering the Sponsors Club platform. It orchestrates user onboarding, organisation and collaborator management, athlete rosters, contract workflows, sponsorship analytics, messaging, and entitlement-aware permissions behind a unified JWT-secured interface.

## Table of contents
- [Project overview](#project-overview)
- [Tech stack](#tech-stack)
- [Domain capabilities](#domain-capabilities)
- [Architecture highlights](#architecture-highlights)
- [Local development quickstart](#local-development-quickstart)
- [Container workflow](#container-workflow)
- [Database seeding](#database-seeding)
- [Tests & quality](#tests--quality)
- [API documentation](#api-documentation)
- [Background jobs](#background-jobs)
- [Project layout](#project-layout)
- [Further reading](#further-reading)
- [License](#license)

## Project overview
Sponsors Club connects athletes, their representatives, and sponsoring organisations. This backend exposes REST endpoints and proof-of-concept HTML clients that cover the entire lifecycle from registration to analytics reporting. Feature entitlements ensure each subscription plan only accesses the functionality it pays for, while role-driven permissions protect sensitive operations.

## Tech stack
- **Framework:** Django 4.2 with Django REST Framework for API development.
- **Auth:** `djangorestframework-simplejwt` for stateless access and refresh tokens, layered on top of Django sessions for admin access.
- **Filtering & pagination:** `django-filter` and DRF’s pagination classes for consistent list endpoints.
- **Schema:** `drf-yasg` renders interactive OpenAPI documentation under `/api/docs/` and `/api/redoc/`.
- **Task utilities:** Structured logging helpers for synchronous analytics sync jobs, ready to be upgraded to Celery workers.
- **Deployment:** Gunicorn entrypoint and Docker image configured for non-root execution.

## Domain capabilities
Each business area is encapsulated in its own Django app and documented under `docs/domain/`.

| App | Responsibilities |
| --- | --- |
| `users` | Custom user model, JWT login/refresh, `/api/users/register/`, `/api/users/me/`, `/api/users/me/roles/`, and entitlement discovery through `/api/users/me/entitlements/`.
| `organisations` | Organisation records, collaborator invitations, quota enforcement, and subscription-aware permissions for managing teams.
| `athletes` | Athlete profiles, sport taxonomy, agent assignments, and subscription limits enforced at the serializer level.
| `follows` | Follow relationships between agents and athletes with plan-based quota checks and list/create/delete APIs.
| `messaging` | Threaded conversations, message posting, pagination helpers, and plan requirements for initiating chats.
| `notifications` | User notification feed with read/unread filtering and entitlement validation before delivery.
| `contracts` | Clause templates, contract versioning workflow, status transitions, and document rendering endpoints for collaborators.
| `analytics` | Social platform catalogues, athlete social accounts, daily stats aggregation, reporting endpoints, and admin-triggered syncs.
| `payments` | Subscription plans, exclusivity rules between agents and organisations, purchase/cancellation flows, and Stripe webhook handlers.

## Architecture highlights
- **JWT authentication pipeline:** `/api/users/login/` issues access and refresh tokens, `/api/users/refresh/` renews sessions, and `/api/users/me/` exposes profile metadata alongside role and entitlement builders.
- **Feature entitlements:** A `FeatureRequirement` matrix evaluates active subscriptions via `feature_status_for_user`, returning machine-readable allow/deny payloads consumed by both API and UI clients.
- **Shared integrations:** Consistent serializer patterns, filter backends, and pagination defaults keep endpoints predictable across apps.
- **Proof-of-concept UI:** HTML templates at `/poc/login/` and `/poc/messaging/` demonstrate JWT flows and messaging interactions against the live API.

## Local development quickstart
1. **Clone and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.dev.txt
   ```
2. **Apply migrations**
   ```bash
   python manage.py migrate
   ```
3. **Create an admin (optional)**
   ```bash
   python manage.py createsuperuser
   ```
4. **Run the server**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```
   Visit `http://127.0.0.1:8000/` for the API root and `/admin/` for the Django admin.

## Container workflow
Build the production-style image and run it locally:
```bash
docker build -t sponsors-club-backend .
docker run --rm -p 8000:8000 \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD=Passw0rd! \
  sponsors-club-backend
```
`PORT` overrides the Gunicorn bind address, while `scripts/migrate.sh` and `scripts/entrypoint.sh` manage database migrations and server startup inside the container.

## Database seeding
Populate a realistic dataset for demos or development:
```bash
python manage.py seed
```
Flags such as `--agents`, `--organisations`, `--athletes`, and `--seed` control dataset volume and determinism. The command creates agents, organisations with collaborators, sports, athletes, and 30 days of social analytics per athlete.

## Tests & quality
Run the test suite (coverage enabled by default):
```bash
pytest
```
Target individual modules with `pytest path/to/test.py -k "filter"`. Optional static analysis is available through Ruff:
```bash
ruff check .
```

## API documentation
With `drf-yasg` installed (included in `requirements.txt`), interactive documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`

## Background jobs
`analytics/tasks.py` provides `fetch_account_stats` and `sync_all_accounts` helpers used by administrator-only endpoints to refresh analytics data. They log progress synchronously today and can be wrapped with Celery (or a similar worker) when asynchronous execution is required. Until then, scheduled runs can call the functions directly from a cron job or management command.

## Project layout
```
├── analytics/           # Social analytics models, APIs, and sync tasks
├── athletes/            # Athlete domain models, serializers, and views
├── contracts/           # Contract workflow and document rendering
├── follows/             # Follow relationships and quota enforcement
├── messaging/           # Threads, messages, and permissions
├── notifications/       # Notification feed and read-state filtering
├── organisations/       # Organisation/collaborator management
├── payments/            # Subscription plans and Stripe webhook handlers
├── users/               # Custom user model, auth, and JWT endpoints
├── docs/                # Detailed platform documentation
├── scripts/             # Docker entrypoint and migration helpers
└── templates/           # Proof-of-concept HTML clients
```

## Further reading
The `docs/` directory expands on every topic covered here:
- [Architecture](docs/architecture/overview.md) — request flow, authentication, integration patterns, and feature entitlements.
- [Domain guides](docs/domain/) — models, permissions, and API contracts for each app.
- [Operations & setup](docs/setup/local-development.md) — environment preparation, Docker usage, and seeding.
- [Testing](docs/testing.md) — pytest configuration, fixtures, and linting tips.
- [Proof-of-concept templates](docs/poc/README.md) — how to exercise the bundled JWT login and messaging demos.

## License
Distributed under the [MIT License](LICENSE).
