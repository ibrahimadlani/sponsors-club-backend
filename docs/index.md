# Sponsors Club Backend – Documentation Hub

Welcome to the central reference for the Sponsors Club backend. The repository is organised so that developers can jump straight to the information needed to build, test, or operate the platform.

## Quick facts
- **Runtime:** Python 3.11, Django 4.2, Django REST Framework, django-filter.
- **Auth stack:** Session auth for staff/UI flows plus JWT tokens via `djangorestframework_simplejwt` for API clients.
- **Primary datastore:** SQLite in development, PostgreSQL in production (configured through `DATABASES` environment overrides). Migrations run with standard Django commands or the provided helper scripts.
- **API documentation:** Install `drf-yasg` to expose `/api/schema/`, `/api/docs/` (Swagger UI), and `/api/redoc/`.
- **Core project module:** `core/` contains settings, routing, custom permissions, and reusable utilities shared across domain apps.

## How the documentation is organised

### 1. Getting started
- [Local development setup](setup/local-development.md)
- [Database seeding guide](setup/data-seeding.md)
- [Testing strategy and tooling](testing.md)

### 2. Architecture & platform internals
- [Architecture overview](architecture/overview.md)
- [Authentication flows & security](architecture/authentication.md)
- [Integrations & external touchpoints](architecture/integration.md)
- [Data model reference](architecture/data-model.md)
- [Feature entitlement engine](architecture/feature-entitlements.md)

### 3. Domain guides
Each domain app has a dedicated chapter that covers models, API contracts, permissions, and interactions with other areas of the platform.
- [Analytics](domain/analytics.md)
- [Analytics permissions](domain/analytics-permissions.md)
- [Athletes](domain/athletes.md)
- [Contracts](domain/contracts.md)
- [Follows](domain/follows.md)
- [Messaging](domain/messaging.md)
- [Notifications](domain/notifications.md)
- [Organisations](domain/organisations.md)
- [Payments](domain/payments.md)
- [Users](domain/users.md)

### 4. Operations & delivery
- [Deployment runbook](operations/deployment.md)
- [Background jobs & scheduled tasks](operations/background-jobs.md)

### 5. Reference & exploratory material
- [Feature entitlements quick reference](feature-entitlements.md)
- [Proof-of-concept HTML flows](poc/README.md)

## Navigating the API
The global router (`core/urls.py`) mounts domain routes under `/api/…`. Refer to the architecture overview for a full map of URL namespaces and to the domain guides for per-resource contracts. Two HTML proof-of-concept views live under `/poc/` for manual testing.

> **Tip:** Each Markdown file is intentionally self-contained—follow links within a section to drill down without jumping back to this index.
