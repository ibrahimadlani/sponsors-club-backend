"""Business logic helpers for analytics reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from django.utils import timezone

from athletes.models import Athlete

from analytics.models import AthleteSocialAccount, DailyStats


@dataclass
class DateRange:
    """Simple value object representing a requested reporting window."""

    label: str
    start: Optional[date]
    end: date


def parse_range(range_param: Optional[str]) -> DateRange:
    """Convert shorthand range strings (e.g. ``30d``) into real dates."""

    end = timezone.now().date()
    if not range_param:
        return DateRange(label="last_30_days", start=end - timedelta(days=29), end=end)

    cleaned = range_param.lower().strip()
    if cleaned.endswith("d") and cleaned[:-1].isdigit():
        days = int(cleaned[:-1])
        days = max(1, min(days, 365))
        return DateRange(
            label=f"last_{days}_days",
            start=end - timedelta(days=days - 1),
            end=end,
        )

    return DateRange(label="all_time", start=None, end=end)


def followers_growth(stats: Iterable[DailyStats]) -> int:
    """Return the numeric growth between the first and last data point."""

    ordered = list(stats)
    if not ordered:
        return 0
    return int(ordered[-1].followers - ordered[0].followers)


def average_engagement_rate(stats: Iterable[DailyStats]) -> float:
    """Compute the arithmetic mean engagement rate for the period."""

    ordered = list(stats)
    if not ordered:
        return 0.0
    average = sum(stat.engagement_rate for stat in ordered) / len(ordered)
    return round(float(average), 2)


def total_posts(stats: Iterable[DailyStats]) -> int:
    """Sum total posts created during the reporting window."""

    return sum(stat.posts_count for stat in stats)


def top_post(stats: Iterable[DailyStats]) -> Optional[Dict[str, object]]:
    """Identify the top performing post based on engagement rate."""

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
    """Return daily points suitable for plotting."""

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
    """Assemble the JSON payload exposed by the summary endpoint."""

    stats_list = list(stats)
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
    """Return the most recent stat entry for an account if available."""

    return account.daily_stats.order_by("-date").first()


def _platform_snapshot(
    account: AthleteSocialAccount, stat: DailyStats
) -> Dict[str, float]:
    return {
        "followers": float(stat.followers),
        "engagement_rate": round(float(stat.engagement_rate), 2),
        "posts_count": float(stat.posts_count),
        "likes": float(stat.likes),
        "comments": float(stat.comments),
    }


def collect_platform_metrics(athlete: Athlete) -> Dict[str, Dict[str, float]]:
    """Return the latest stat per platform for the given athlete."""

    metrics: Dict[str, Dict[str, float]] = {}
    accounts = athlete.social_accounts.filter(is_active=True).select_related("platform")
    for account in accounts:
        stat = latest_metrics(account)
        if not stat:
            continue
        metrics[account.platform.get_name_display()] = _platform_snapshot(account, stat)
    return metrics


def summarise_totals(metrics: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Aggregate metrics across all platforms for easier comparison."""

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
    """Craft a comparison structure for the two supplied athletes."""

    primary_metrics = collect_platform_metrics(primary)
    secondary_metrics = collect_platform_metrics(secondary)
    primary_totals = summarise_totals(primary_metrics)
    secondary_totals = summarise_totals(secondary_metrics)

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
