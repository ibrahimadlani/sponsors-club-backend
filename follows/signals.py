"""Signal handlers for keeping cached follower counts in sync."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from athletes.models import Athlete

from .models import Follow


def _refresh_followers_count(athlete_id: str) -> None:
    """Update cached follow counts for a specific athlete.

    Args:
        athlete_id: Primary key of the athlete whose cached follower count
            should be recalculated.
    """

    follower_total = Follow.objects.filter(athlete_id=athlete_id).count()
    # Storing the aggregate on the athlete helps render dashboards without
    # issuing expensive count queries for every request.
    Athlete.objects.filter(id=athlete_id).update(followers_count_cached=follower_total)


@receiver(post_save, sender=Follow)
def update_followers_count_on_save(sender=None, instance=None, **_kwargs):
    """Handle create/update events by recalculating cached counts.

    Args:
        sender: Model class that triggered the signal or ``None`` when the
            helper is invoked directly (unused).
        instance: Follow instance that was created or updated. The guard keeps
            defensive parity with direct invocations used in tests.
        **_kwargs: Additional signal metadata ignored by this handler.
    """

    # ``sender`` is part of Django's signal contract but isn't needed when
    # recalculating the follower cache.
    _ = sender
    if instance is None:
        return
    _refresh_followers_count(instance.athlete_id)


@receiver(post_delete, sender=Follow)
def update_followers_count_on_delete(sender=None, instance=None, **_kwargs):
    """Handle deletions by recalculating cached counts.

    Args:
        sender: Model class that triggered the signal or ``None`` when the
            helper is invoked directly (unused).
        instance: Follow instance that was removed. The guard keeps defensive
            parity with direct invocations used in tests.
        **_kwargs: Additional signal metadata ignored by this handler.
    """

    # ``sender`` is part of Django's signal contract but isn't needed when
    # recalculating the follower cache.
    _ = sender
    if instance is None:
        return
    _refresh_followers_count(instance.athlete_id)
