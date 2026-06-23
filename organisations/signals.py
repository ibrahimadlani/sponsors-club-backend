"""Signals for organisations app to maintain invariants."""

from __future__ import annotations

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Collaborator


@receiver(post_delete, sender=Collaborator)
def delete_organisation_when_owner_removed(sender, instance: Collaborator, **kwargs):
    """No-op: organisations persist even when owner collaborators are removed.

    The application logic handles owner absence explicitly in endpoints. This
    avoids surprising deletions in flows that temporarily remove collaborators.
    """
    return
