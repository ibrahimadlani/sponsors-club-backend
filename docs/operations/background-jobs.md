# Background jobs & scheduling

The codebase includes task helpers for the analytics domain and leaves hooks to
integrate a real job runner (Celery, RQ, cron). This document summarises the
current state and outlines next steps when wiring in an asynchronous worker.

## Existing task stubs
The module [`analytics/tasks.py`](../../analytics/tasks.py) defines two helpers:

- `fetch_account_stats(account_id)` resolves an active `AthleteSocialAccount`,
  logs that a sync should run, and returns `None`. The function is synchronous on
  purpose so unit tests and admin-triggered actions can call it without a queue.
- `sync_all_accounts()` iterates every active social account and invokes
  `fetch_account_stats` for each entry while recording progress in the logger.

Both functions are imported by `analytics.views.FetchAccountStatsView` and
`SyncAllAccountsView`, giving administrators `/api/analytics/accounts/<id>/fetch/`
(POST) and `/api/analytics/accounts/sync_all/` (POST) endpoints to start a refresh
manually.

## Integrating a worker
When you are ready to move the workload off the web process:

1. **Pick a backend:** Celery with Redis or RabbitMQ is the recommended option.
2. **Wrap the stubs:** decorate the functions with `@shared_task` (Celery) and
   update the views to call `.delay(...)` instead of executing them inline.
3. **Configure retries and timeouts:** ensure transient API failures are retried
   and guard against long-running fetches.
4. **Monitor execution:** emit structured logs (already present) and, if possible,
   push task metrics to your observability stack.

The synchronous functions can remain importable so that management commands or
unit tests keep calling them directly when no worker is running.

## Scheduling periodic syncs
Until Celery beat (or an equivalent scheduler) is enabled you can:

- run `python manage.py shell -c "from analytics.tasks import sync_all_accounts; sync_all_accounts()"`
  from a cron job, or
- call the admin endpoints listed above using an internal automation token.

Once a scheduler is in place, plan for an hourly or daily run depending on how
fresh social metrics need to be for the product experience.
