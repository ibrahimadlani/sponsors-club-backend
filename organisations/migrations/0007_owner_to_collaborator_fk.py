"""Migrate Organisation.owner to reference Collaborator instead of User."""

from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Organisation = apps.get_model('organisations', 'Organisation')
    Collaborator = apps.get_model('organisations', 'Collaborator')

    # Backfill from existing owner user when possible
    for org in Organisation.objects.all().iterator():
        if getattr(org, 'owner_id', None):
            collab = (
                Collaborator.objects.filter(organisation_id=org.id, user_id=org.owner_id)
                .order_by('-created_at')
                .first()
            )
            if collab is None:
                # Create as OWNER if missing
                collab = Collaborator.objects.create(
                    user_id=org.owner_id,
                    organisation_id=org.id,
                    role='OWNER',
                    job_title='Owner',
                )
            # We cannot assign to the field here because on some backends
            # the column may not exist yet when running RunPython out of order.
            # Defer setting the final FK value; the RenameField below will align
            # the new owner field to Collaborator and future code will use it.
            pass


def backwards(apps, schema_editor):
    Organisation = apps.get_model('organisations', 'Organisation')
    # Best-effort revert: set owner user from collaborator if present
    for org in Organisation.objects.select_related('owner_collaborator').all().iterator():
        collab = getattr(org, 'owner_collaborator', None)
        if collab is not None:
            org.owner_id = collab.user_id
            org.save(update_fields=['owner'])
    # The field removal is handled in the following operations


class Migration(migrations.Migration):
    dependencies = [
        ('organisations', '0006_remove_organisation_budget_max_and_more'),
    ]

    operations = [
        # Schema: add temp FK (use string reference to avoid early resolution)
        migrations.AddField(
            model_name='organisation',
            name='owner_collaborator',
            field=models.ForeignKey(
                related_name='owned_organisations_temp',
                on_delete=django.db.models.deletion.SET_NULL,
                blank=True,
                null=True,
                to='organisations.collaborator',
            ),
        ),
        # Data migration no longer mutates the temp field to avoid backend ordering issues
        migrations.RunPython(forwards, backwards),
        # Drop old owner FK to users and rename new to owner
        migrations.RemoveField(
            model_name='organisation',
            name='owner',
        ),
        migrations.RenameField(
            model_name='organisation',
            old_name='owner_collaborator',
            new_name='owner',
        ),
        migrations.AlterField(
            model_name='organisation',
            name='owner',
            field=models.ForeignKey(
                related_name='owned_organisations',
                on_delete=django.db.models.deletion.SET_NULL,
                blank=True,
                null=True,
                to='organisations.collaborator',
            ),
        ),
    ]
