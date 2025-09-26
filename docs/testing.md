# Testing guide

The project uses `pytest` with `pytest-django` for unit and integration tests. Coverage reporting is enabled by default so you can continuously evaluate code health.

## Running the full suite
```bash
pytest
```
`pytest.ini` configures discovery patterns (`tests.py`, `test_*.py`, `*_tests.py`) and adds `--cov=. --cov-report=term-missing` to every invocation, producing per-file coverage output across the entire Django project.

To narrow the scope to a single module or test, provide its import path:
```bash
pytest organisations/tests/test_api.py -k "invites"
```

## Database behaviour
- Tests that interact with the ORM must declare `@pytest.mark.django_db`. This marker is documented in `pytest.ini` and ensures Django sets up the test database automatically.
- A global `reset_db` fixture (defined in `conftest.py`) flushes the database after each test, guaranteeing isolation without requiring manual cleanup.

## Built-in fixtures
`conftest.py` defines reusable fixtures to accelerate test authoring:
- `api_client`: provides DRF's `APIClient` for authenticated or anonymous requests.
- `agent_user`: creates a custom user with the `AGENT` account type and an attached `AgentProfile`.
- `organisations_setup`: seeds an organisation, collaborator owner, and an active subscription using the default plans created by migrations.
- `agent_subscription` and `organisation_subscription`: shortcuts to provision active subscriptions for entitlement checks.

Import these fixtures into your tests by naming them as function arguments. Pytest injects them automatically.

## Static analysis (optional)
Use Ruff to lint and format the codebase:
```bash
ruff check .
```
Although not enforced by CI yet, running Ruff locally helps catch style issues before committing changes.
