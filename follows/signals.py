"""Signal handlers for keeping cached follower counts in sync."""

# pylint: disable=no-member

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from athletes.models import Athlete

from .models import Follow


def _refresh_followers_count(athlete_id: str) -> None:
    """Update the cached follower count for the given athlete."""

    follower_total = Follow.objects.filter(athlete_id=athlete_id).count()
    Athlete.objects.filter(id=athlete_id).update(followers_count_cached=follower_total)


@receiver(post_save, sender=Follow)
def update_followers_count_on_save(_sender, instance, **_kwargs):
    """Refresh cached follower counts whenever a follow is created or updated."""

    _refresh_followers_count(instance.athlete_id)


@receiver(post_delete, sender=Follow)
def update_followers_count_on_delete(_sender, instance, **_kwargs):
    """Refresh cached follower counts whenever a follow is removed."""

    _refresh_followers_count(instance.athlete_id)
