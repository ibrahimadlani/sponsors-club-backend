# Analytics domain

## Overview
The analytics app models social media accounts linked to athletes and exposes
REST endpoints for retrieving daily performance metrics, aggregated summaries,
and comparisons between athletes. It also includes service helpers for
assembling reporting payloads and stubs for background synchronisation jobs.

## Data model
- **`SocialPlatform`** enumerates the supported networks (TikTok, Instagram,
  Facebook, YouTube) and stores an optional `base_url` for deep-linking.
- **`AthleteSocialAccount`** joins an `Athlete` to a `SocialPlatform`, enforcing
  a single account per athlete/platform combination via
  `unique_account_per_platform`. The model persists external identifiers,
  access tokens, and an `is_active` flag used by sync routines.
- **`DailyStats`** captures time-series metrics (`followers`, `posts_count`,
  `likes`, `comments`, etc.) for each social account. The model recomputes its
  `engagement_rate` on every save and supplies a `for_range` queryset helper for
  date filtering. Uniqueness is enforced per `(account, date)`.

## Serializers
- `DailyStatsSerializer` exposes the raw metrics and nests account/platform
  information through `AthleteSocialAccountSerializer` and
  `SocialPlatformSerializer`.
- `DailyStatsSummarySerializer` validates the aggregated payload assembled by
  the report services (followers growth, average engagement, total posts,
  top-performing post, and graph data).

## Reporting services
`analytics.services.reports` contains the reusable logic that underpins the
summary and comparison endpoints:

- `parse_range()` converts shortcuts like `30d` into `DateRange` objects.
- `build_summary_payload()` rolls up stats for a single athlete/platform,
  computing growth deltas, averages, and chart points.
- `build_comparison_payload()` contrasts two athletes by platform and totals,
  returning per-platform differences across followers, engagement rate, and
  content volume.

## Background tasks
Two synchronous stubs in `analytics.tasks` define the contract for future
workers:

- `fetch_account_stats(account_id)` resolves an active social account and logs
  that a sync should occur. It currently returns `None`, ready to be replaced by
  Celery-backed collectors.
- `sync_all_accounts()` iterates all active accounts and invokes
  `fetch_account_stats`, allowing admin-triggered bulk refreshes.

## API surface
All routes are registered under `/api/analytics/`:

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/athletes/<athlete_id>/stats/` | Paginated `DailyStats` records with optional `?platform=` filter. | Authenticated |
| `GET` | `/athletes/<athlete_id>/stats/summary/` | Aggregated payload for the athlete's first active account within an optional `?range=` (defaults to last 30 days). | Authenticated |
| `GET` | `/athletes/<athlete_id>/compare/<other_id>/` | Comparison snapshot between two athletes across their platforms. | Authenticated |
| `POST` | `/accounts/<account_id>/fetch/` | Trigger a fetch for a single social account. | Admin only |
| `POST` | `/accounts/sync_all/` | Launch a bulk sync across all active accounts. | Admin only |

Pagination defaults to 30 items per page with an upper cap of 100 via
`DailyStatsPagination`.

## Permissions and access control
Analytics read endpoints require an authenticated user. Write-style triggers
(`fetch` and `sync_all`) are restricted to admin or superuser accounts. For
object-level authorisation around write operations on analytics resources, use
`analytics.permissions.IsAgentOrStaff`, documented separately alongside other
feature-governed checks.
