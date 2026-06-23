"""Add slug field to Athlete and backfill existing rows."""

import uuid

from django.db import migrations, models
from django.db.models import Q
from django.utils.text import slugify


def populate_athlete_slugs(apps, schema_editor):
    Athlete = apps.get_model("athletes", "Athlete")

    for athlete in Athlete.objects.filter(Q(slug__isnull=True) | Q(slug="")):
        base_slug = slugify(athlete.full_name) or uuid.uuid4().hex[:8]
        slug = base_slug
        counter = 1
        while Athlete.objects.filter(slug=slug).exclude(pk=athlete.pk).exists():
            counter += 1
            slug = f"{base_slug}-{counter}"
        athlete.slug = slug
        athlete.save(update_fields=["slug", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("athletes", "0008_athlete_gallery_and_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="slug",
            field=models.SlugField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(populate_athlete_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="athlete",
            name="slug",
            field=models.SlugField(blank=True, max_length=255, unique=True),
        ),
    ]
