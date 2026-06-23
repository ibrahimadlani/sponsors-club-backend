"""Add athlete location fields and gallery photos."""

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("athletes", "0007_update_sportdiscipline_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="city",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="athlete",
            name="country",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.CreateModel(
            name="AthletePhoto",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image", models.ImageField(upload_to="athlete_gallery/")),
                ("caption", models.CharField(blank=True, max_length=255)),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="athletes.athlete",
                    ),
                ),
            ],
            options={
                "ordering": ("position", "created_at"),
            },
        ),
    ]
