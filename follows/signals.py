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
def update_followers_count_on_save(_sender, instance, **_kwargs):
    """Handle create/update events by recalculating cached counts.

    Args:
        _sender: Model class that triggered the signal (unused).
        instance: Follow instance that was created or updated.
        **_kwargs: Additional signal metadata ignored by this handler.
    """

    _refresh_followers_count(instance.athlete_id)


@receiver(post_delete, sender=Follow)
def update_followers_count_on_delete(_sender, instance, **_kwargs):
    """Handle deletions by recalculating cached counts.

    Args:
        _sender: Model class that triggered the signal (unused).
        instance: Follow instance that was removed.
        **_kwargs: Additional signal metadata ignored by this handler.
    """

    _refresh_followers_count(instance.athlete_id)
