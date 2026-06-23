"""Merge migrations 0007 and 0008 for organisations app."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("organisations", "0007_owner_to_collaborator_fk"),
        ("organisations", "0008_collaborator_collab_user_created_idx"),
    ]

    operations = []
