# `analytics/` — Social media statistics tracking and reporting for athlete accounts.

## Responsibility

- Link athlete profiles to their social media accounts (TikTok, Instagram, Facebook, YouTube).
- Store daily aggregated metrics and compute engagement rate.
- Provide summary, comparison, and date-range query endpoints.
- Support manual and bulk stat fetch from social platforms.

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `SocialPlatform` | Supported social network | `name` (TIKTOK / INSTAGRAM / FACEBOOK / YOUTUBE), `base_url` |
| `AthleteSocialAccount` | Athlete's account on a platform | `athlete`, `platform`, `username`, `external_id`, `access_token`, `is_active`; unique per (athlete, platform) |
| `DailyStats` | Daily aggregated metrics | `account`, `date`, `followers`, `likes`, `comments`, `shares`, `views`, `engagement_rate` (computed); `compute_engagement_rate()`, `save()` |
| `DailyStatsQuerySet` | Time-range filtering | `.for_range(start_date, end_date)` |

`engagement_rate` is recalculated on every `save()` as
`(likes + comments + shares) / followers × 100`, rounded to 4 decimal places.

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `GET` | `/api/analytics/athletes/<uuid>/stats/` | Required | `IsAuthenticated` | Daily stats (supports `?start_date=`, `?end_date=`) |
| `GET` | `/api/analytics/athletes/<uuid>/stats/summary/` | Required | `IsAuthenticated` | Summary statistics for an athlete |
| `GET` | `/api/analytics/athletes/<uuid>/compare/<uuid>/` | Required | `IsAuthenticated` | Side-by-side comparison of two athletes |
| `POST` | `/api/analytics/accounts/<uuid>/fetch/` | Required | `IsAgentOrStaff` | Fetch latest stats for one account |
| `POST` | `/api/analytics/accounts/sync_all/` | Required | `IsAdminUser` | Bulk-sync all active accounts |

## Permissions & Roles

- **`IsAuthenticated`** — required for all read endpoints.
- **`IsAgentOrStaff`** (`core.permissions`) — required for triggering a stat fetch.
  Prevents collaborators from triggering API calls to social platforms.
- **`IsAdminUser`** — required for the bulk sync endpoint.

## Key Workflows

1. **Account linking** — Admin or agent creates an `AthleteSocialAccount` with the
   athlete's platform username and `external_id`.
2. **Stat fetch** — `POST /accounts/<uuid>/fetch/` calls the platform API, creates or
   updates a `DailyStats` record for today, and updates `Athlete.followers_count_cached`
   and `engagement_rate_cached`.
3. **Bulk sync** — `POST /accounts/sync_all/` iterates all active accounts and triggers
   individual fetches; intended for scheduled background jobs.
4. **Reporting** — `GET /athletes/<uuid>/stats/` returns a date-range filtered queryset
   via `DailyStatsQuerySet.for_range()`.

## Dependencies

**Requires:** `athletes` (Athlete, which is updated with cached metrics)

**Used by:** `athletes` (cached metrics on `Athlete` model update)
