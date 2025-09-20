"""Add explicit owner foreign key to organisations."""


from django.conf import settings
from django.db import migrations, models


def set_existing_owners(apps, schema_editor):
    Organisation = apps.get_model('organisations', 'Organisation')
    Collaborator = apps.get_model('organisations', 'Collaborator')

    for organisation in Organisation.objects.filter(owner__isnull=True):
        owner_collaborator = (
            Collaborator.objects
            .filter(organisation_id=organisation.id, role='OWNER')
            .order_by('created_at')
            .first()
        )
        if owner_collaborator is not None:
            organisation.owner_id = owner_collaborator.user_id
            organisation.save(update_fields=['owner'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_update_account_type_to_collaborator'),
        ('organisations', '0004_organisation_description_organisation_website'),
    ]

    operations = [
        migrations.AddField(
            model_name='organisation',
            name='owner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='owned_organisations',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(set_existing_owners, migrations.RunPython.noop),
    ]
