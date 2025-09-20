"""Async task stubs for synchronising social media analytics."""

from __future__ import annotations

import logging
from typing import Optional

from django.utils import timezone

from .models import AthleteSocialAccount, DailyStats

logger = logging.getLogger(__name__)


def fetch_account_stats(account_id) -> Optional[DailyStats]:
    """Fetch the latest stats for a social account.

    The implementation is intentionally lightweight: it resolves the account and
    logs that a sync should occur. The future Celery task can replace the body
    of this function with real API calls without changing the public contract.
    """

    try:
        account = AthleteSocialAccount.objects.get(id=account_id, is_active=True)
    except AthleteSocialAccount.DoesNotExist:  # pragma: no cover - defensive guard
        logger.warning("Account %s not found or inactive", account_id)
        return None

    logger.info(
        "Fetching stats for %s on %s", account.username, account.platform.get_name_display()
    )
    # TODO: Integrate with TikTok/Instagram/Facebook/YouTube API clients.
    # The returned DailyStats instance (or None) allows callers to inspect the
    # outcome. For now we return ``None`` to indicate the fetch is not yet
    # implemented.
    return None


def sync_all_accounts() -> None:
    """Iterate all active accounts and fetch their latest stats."""

    account_ids = list(
        AthleteSocialAccount.objects.filter(is_active=True).values_list("id", flat=True)
    )
    logger.info("Starting bulk sync for %s accounts", len(account_ids))
    for account_id in account_ids:
        fetch_account_stats(account_id)
    logger.info("Completed bulk sync run at %s", timezone.now())
