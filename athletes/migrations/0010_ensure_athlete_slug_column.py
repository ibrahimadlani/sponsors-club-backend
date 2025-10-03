"""Ensure athlete slug column exists for legacy databases."""

import uuid

from django.db import migrations, models
from django.db.models import Q
from django.utils.text import slugify


def ensure_slug_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = "athletes_athlete"

    with connection.cursor() as cursor:
        try:
            columns = connection.introspection.get_table_description(cursor, table_name)
        except Exception:  # pragma: no cover - table missing entirely
            return

    if any(column.name == "slug" for column in columns):
        return

    Athlete = apps.get_model("athletes", "Athlete")

    field_with_default = models.SlugField(
        max_length=255,
        blank=True,
        default="",
    )
    field_with_default.set_attributes_from_name("slug")
    schema_editor.add_field(Athlete, field_with_default)

    field_without_default = models.SlugField(
        max_length=255,
        blank=True,
    )
    field_without_default.set_attributes_from_name("slug")
    schema_editor.alter_field(
        Athlete,
        field_with_default,
        field_without_default,
    )


def populate_missing_slugs(apps, schema_editor):
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

    connection = schema_editor.connection
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, "athletes_athlete")

    has_unique_constraint = any(
        details.get("unique") and details.get("columns") == ["slug"]
        for details in constraints.values()
    )

    if not has_unique_constraint:
        field_without_unique = models.SlugField(
            max_length=255,
            blank=True,
        )
        field_without_unique.set_attributes_from_name("slug")
        field_with_unique = models.SlugField(
            max_length=255,
            blank=True,
            unique=True,
        )
        field_with_unique.set_attributes_from_name("slug")
        schema_editor.alter_field(
            Athlete,
            field_without_unique,
            field_with_unique,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("athletes", "0009_athlete_slug"),
    ]

    operations = [
        migrations.RunPython(ensure_slug_column, migrations.RunPython.noop),
        migrations.RunPython(populate_missing_slugs, migrations.RunPython.noop),
    ]
