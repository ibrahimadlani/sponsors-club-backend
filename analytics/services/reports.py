"""Business logic helpers for analytics reports."""

# The helpers in this module transform database level statistics into payloads
# directly consumable by the API responses. The extra documentation and inline
# comments make explicit the reasoning behind each transformation step.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from django.utils import timezone

from athletes.models import Athlete

from analytics.models import AthleteSocialAccount, DailyStats


@dataclass
class DateRange:
    """Simple value object representing a requested reporting window.

    Attributes:
        label: Human readable identifier for the range (e.g. ``last_30_days``).
        start: Earliest date included in the period, if bounded.
        end: Final inclusive date for the reporting window.
    """

    label: str
    start: Optional[date]
    end: date


def parse_range(range_param: Optional[str]) -> DateRange:
    """Convert shorthand range strings into an explicit :class:`DateRange`.

    Args:
        range_param: Raw request parameter such as ``"30d"`` or ``None``.

    Returns:
        DateRange: Normalised range with concrete ``start``/``end`` dates.
    """

    end = timezone.now().date()
    if not range_param:
        # Default to the last 30 days when no explicit parameter is provided.
        return DateRange(label="last_30_days", start=end - timedelta(days=29), end=end)

    cleaned = range_param.lower().strip()
    if cleaned.endswith("d") and cleaned[:-1].isdigit():
        # Clamp the requested day span between 1 and 365 to avoid huge queries.
        days = int(cleaned[:-1])
        days = max(1, min(days, 365))
        return DateRange(
            label=f"last_{days}_days",
            start=end - timedelta(days=days - 1),
            end=end,
        )

    return DateRange(label="all_time", start=None, end=end)


def followers_growth(stats: Iterable[DailyStats]) -> int:
    """Return the numeric growth between the first and last data point.

    Args:
        stats: Iterable of chronological :class:`DailyStats` records.

    Returns:
        int: Difference in follower count across the provided series.
    """

    ordered = list(stats)
    if not ordered:
        return 0
    return int(ordered[-1].followers - ordered[0].followers)


def average_engagement_rate(stats: Iterable[DailyStats]) -> float:
    """Compute the arithmetic mean engagement rate for the period.

    Args:
        stats: Iterable of :class:`DailyStats` snapshots.

    Returns:
        float: Rounded average engagement rate for the supplied data.
    """

    ordered = list(stats)
    if not ordered:
        return 0.0
    average = sum(stat.engagement_rate for stat in ordered) / len(ordered)
    return round(float(average), 2)


def total_posts(stats: Iterable[DailyStats]) -> int:
    """Sum total posts created during the reporting window.

    Args:
        stats: Iterable of :class:`DailyStats` entries.

    Returns:
        int: Number of posts published within the time window.
    """

    return sum(stat.posts_count for stat in stats)


def top_post(stats: Iterable[DailyStats]) -> Optional[Dict[str, object]]:
    """Identify the top performing post based on engagement rate.

    Args:
        stats: Iterable of :class:`DailyStats` objects containing post metadata.

    Returns:
        Optional[Dict[str, object]]: Summary of the best post or ``None`` if
        no suitable candidate exists.
    """

    best: Optional[Dict[str, object]] = None
    best_score = -1.0
    for stat in stats:
        if not stat.top_post:
            continue
        engagement = float(stat.top_post.get("engagement_rate", 0.0))
        if engagement > best_score:
            best_score = engagement
            best = {
                "post_id": stat.top_post.get("post_id"),
                "likes": stat.top_post.get("likes", 0),
                "comments": stat.top_post.get("comments", 0),
                "engagement_rate": round(engagement, 2),
            }
    return best


def graph_points(stats: Iterable[DailyStats]) -> List[Dict[str, object]]:
    """Return daily points suitable for plotting.

    Args:
        stats: Iterable of :class:`DailyStats` instances.

    Returns:
        List[Dict[str, object]]: Minimal serialisable representation of the
        trend data.
    """

    return [
        {
            "date": stat.date,
            "followers": stat.followers,
            "engagement_rate": round(float(stat.engagement_rate), 2),
        }
        for stat in stats
    ]


def build_summary_payload(
    athlete_id,
    account: AthleteSocialAccount,
    stats: Iterable[DailyStats],
    period: DateRange,
) -> Dict[str, object]:
    """Assemble the JSON payload exposed by the summary endpoint.

    Args:
        athlete_id: Identifier of the athlete being summarised.
        account: Social account from which analytics originate.
        stats: Iterable of :class:`DailyStats` values for the requested range.
        period: Normalised time window produced by :func:`parse_range`.

    Returns:
        Dict[str, object]: Full payload consumed by the API serializer.
    """

    stats_list = list(stats)
    # Reuse the lower-level helpers to keep the aggregation logic centralised.
    summary = {
        "followers_growth": float(followers_growth(stats_list)),
        "engagement_rate_avg": average_engagement_rate(stats_list),
        "posts_count": float(total_posts(stats_list)),
    }
    return {
        "athlete_id": athlete_id,
        "platform": account.platform.get_name_display(),
        "period": period.label,
        "summary": summary,
        "top_post": top_post(stats_list),
        "graph_data": graph_points(stats_list),
    }


def latest_metrics(account: AthleteSocialAccount) -> Optional[DailyStats]:
    """Return the most recent stat entry for an account if available.

    Args:
        account: Social account whose metrics should be inspected.

    Returns:
        Optional[DailyStats]: Latest stats record or ``None`` when missing.
    """

    return account.daily_stats.order_by("-date").first()


def _platform_snapshot(
    account: AthleteSocialAccount, stat: DailyStats
) -> Dict[str, float]:
    """Extract core metrics for a single platform snapshot.

    Args:
        account: Social account used mainly for context (platform name).
        stat: The most recent :class:`DailyStats` associated with ``account``.

    Returns:
        Dict[str, float]: Serializable metrics used in summary payloads.
    """

    # Convert decimal based values to floats to keep the payload JSON friendly.
    return {
        "followers": float(stat.followers),
        "engagement_rate": round(float(stat.engagement_rate), 2),
        "posts_count": float(stat.posts_count),
        "likes": float(stat.likes),
        "comments": float(stat.comments),
    }


def collect_platform_metrics(athlete: Athlete) -> Dict[str, Dict[str, float]]:
    """Return the latest stat per platform for the given athlete.

    Args:
        athlete: Athlete whose social accounts should be inspected.

    Returns:
        Dict[str, Dict[str, float]]: Mapping of platform display names to the
        most recent metric snapshot.
    """

    metrics: Dict[str, Dict[str, float]] = {}
    accounts = athlete.social_accounts.filter(is_active=True).select_related("platform")
    # Iterate through all active accounts to build a platform keyed dictionary.
    for account in accounts:
        stat = latest_metrics(account)
        if not stat:
            continue
        metrics[account.platform.get_name_display()] = _platform_snapshot(account, stat)
    return metrics


def summarise_totals(metrics: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Aggregate metrics across all platforms for easier comparison.

    Args:
        metrics: Platform keyed snapshots returned by
            :func:`collect_platform_metrics`.

    Returns:
        Dict[str, float]: Combined totals and averaged engagement rate.
    """

    totals = {"followers": 0.0, "posts_count": 0.0, "likes": 0.0, "comments": 0.0}
    engagement_rates: List[float] = []
    for snapshot in metrics.values():
        totals["followers"] += snapshot.get("followers", 0.0)
        totals["posts_count"] += snapshot.get("posts_count", 0.0)
        totals["likes"] += snapshot.get("likes", 0.0)
        totals["comments"] += snapshot.get("comments", 0.0)
        if snapshot.get("engagement_rate") is not None:
            engagement_rates.append(float(snapshot["engagement_rate"]))
    totals["engagement_rate"] = (
        round(sum(engagement_rates) / len(engagement_rates), 2)
        if engagement_rates
        else 0.0
    )
    return totals


def build_comparison_payload(primary: Athlete, secondary: Athlete) -> Dict[str, object]:
    """Craft a comparison structure for the two supplied athletes.

    Args:
        primary: Athlete considered the baseline in the comparison view.
        secondary: Athlete whose metrics are compared against ``primary``.

    Returns:
        Dict[str, object]: Rich payload with platform and aggregate
        comparisons.
    """

    primary_metrics = collect_platform_metrics(primary)
    secondary_metrics = collect_platform_metrics(secondary)
    primary_totals = summarise_totals(primary_metrics)
    secondary_totals = summarise_totals(secondary_metrics)

    # Gather every platform represented to compare like-for-like snapshots.
    platform_keys = sorted(set(primary_metrics.keys()) | set(secondary_metrics.keys()))
    platform_comparison = {}
    for platform in platform_keys:
        p_snapshot = primary_metrics.get(platform, {})
        s_snapshot = secondary_metrics.get(platform, {})
        platform_comparison[platform] = {
            "followers_difference": p_snapshot.get("followers", 0.0)
            - s_snapshot.get("followers", 0.0),
            "engagement_rate_difference": p_snapshot.get("engagement_rate", 0.0)
            - s_snapshot.get("engagement_rate", 0.0),
            "posts_count_difference": p_snapshot.get("posts_count", 0.0)
            - s_snapshot.get("posts_count", 0.0),
        }

    # Compute the overall delta to expose who leads when aggregating metrics.
    totals_difference = {
        key: primary_totals.get(key, 0.0) - secondary_totals.get(key, 0.0)
        for key in ("followers", "engagement_rate", "posts_count", "likes", "comments")
    }

    return {
        "primary": {
            "athlete_id": str(primary.id),
            "athlete_name": primary.full_name,
            "platforms": primary_metrics,
            "totals": primary_totals,
        },
        "secondary": {
            "athlete_id": str(secondary.id),
            "athlete_name": secondary.full_name,
            "platforms": secondary_metrics,
            "totals": secondary_totals,
        },
        "comparison": {
            "platforms": platform_comparison,
            "totals": totals_difference,
        },
    }
