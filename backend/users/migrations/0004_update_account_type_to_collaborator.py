"""Update stored account type values to use the collaborator label."""

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(account_type="ORGANISATION").update(account_type="COLLABORATOR")


def backwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(account_type="COLLABORATOR").update(account_type="ORGANISATION")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_user_account_type"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
