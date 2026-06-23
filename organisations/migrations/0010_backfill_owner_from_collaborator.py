"""Backfill Organisation.owner FK from existing Collaborator OWNER rows."""

from django.db import migrations


def forwards(apps, schema_editor):
    Organisation = apps.get_model("organisations", "Organisation")
    Collaborator = apps.get_model("organisations", "Collaborator")

    for org in Organisation.objects.filter(owner__isnull=True).iterator():
        collab = (
            Collaborator.objects.filter(organisation_id=org.id, role="OWNER")
            .order_by("created_at")
            .first()
        )
        if collab:
            org.owner_id = collab.id
            org.save(update_fields=["owner"])


def backwards(apps, schema_editor):
    # No-op. We keep the owner linkage; reversing would risk data loss.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("organisations", "0009_merge_0007_0008"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
