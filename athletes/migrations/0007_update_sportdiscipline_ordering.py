"""Update SportDiscipline default ordering to avoid legacy columns."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("athletes", "0006_update_sport_fields"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="sportdiscipline",
            options={
                "ordering": ("name",),
                "unique_together": {("sport", "slug")},
            },
        ),
    ]
