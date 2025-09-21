# Sponsors Club Backend Documentation

## Platform overview
- **Tech stack:** Python 3.11 on Django 4.2 with Django REST Framework and django-filter providing the API backbone. The production container bakes dependencies into a virtual environment and runs Gunicorn via the `scripts/entrypoint.sh` helper.
- **Database:** SQLite is the default development database, with migrations applied through standard Django management commands or the bundled `scripts/migrate.sh` script for containerized deployments.
- **Authentication:** Session authentication coexists with JWT tokens from `djangorestframework_simplejwt`, giving first-party clients and external integrations flexible login flows.
- **Interactive docs:** When `drf-yasg` is installed (it is included in `requirements.txt`), interactive OpenAPI documentation is served at `/api/docs/` and `/api/redoc/`.

## Application map
| App | Responsibility |
| --- | -------------- |
| `analytics` | Models and APIs to sync and expose athlete social metrics and reports. |
| `athletes` | Athlete and sport profiles, including entitlement-aware serializers. |
| `contracts` | Contract templates, revisions, and workflow management. |
| `follows` | Follow relationships between organisations and athletes, with quota enforcement. |
| `messaging` | Threaded conversations, message serialization, and permissions. |
| `notifications` | User-facing notifications with read-state tracking. |
| `organisations` | Organisation records, collaborators, invitations, and related APIs. |
| `payments` | Subscription plans, billing state, and entitlement evaluation helpers. |
| `users` | Custom user model, registration, login, role discovery, and JWT endpoints. |

Core project configuration lives in `core/` (settings, URL routing, WSGI), and shared fixtures plus demo tooling are implemented under `core/management/commands/`.

## API surface
The project-level router (`core/urls.py`) wires each domain app under the `/api/` prefix, exposes authentication helpers under `/api/users/`, payment and notification namespaces, and provides two proof-of-concept HTML templates at `/poc/login/` and `/poc/messaging/` for manual workflows.

## Documentation index
- [Local development setup](setup/local-development.md)
- [Database seeding](setup/data-seeding.md)
- [Testing guide](testing.md)
- [Feature entitlements reference](feature-entitlements.md)

Each guide focuses on actionable steps. Domain- and architecture-specific chapters can build upon this foundation using the same folder structure (`architecture/`, `domain/`, `operations/`, etc.).
