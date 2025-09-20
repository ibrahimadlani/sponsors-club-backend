from __future__ import annotations

from django.db import migrations


def ensure_clause_template_columns(apps, schema_editor):
    """Backfill missing ClauseTemplate columns for pre-existing databases."""

    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    table_name = ClauseTemplate._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

    statements: list[str] = []

    if "category" not in existing_columns:
        statements.append(
            f"ALTER TABLE {schema_editor.quote_name(table_name)} "
            f"ADD COLUMN {schema_editor.quote_name('category')} varchar(32) NOT NULL DEFAULT 'administratives'"
        )

    if "version" not in existing_columns:
        statements.append(
            f"ALTER TABLE {schema_editor.quote_name(table_name)} "
            f"ADD COLUMN {schema_editor.quote_name('version')} integer NOT NULL DEFAULT 1"
        )

    if "is_active" not in existing_columns:
        bool_default = "1" if connection.vendor == "sqlite" else "true"
        statements.append(
            f"ALTER TABLE {schema_editor.quote_name(table_name)} "
            f"ADD COLUMN {schema_editor.quote_name('is_active')} boolean NOT NULL DEFAULT {bool_default}"
        )

    if "placeholders" not in existing_columns:
        if connection.vendor == "sqlite":
            column_type = "text"
            default = "'[]'"
        elif connection.vendor == "postgresql":
            column_type = "jsonb"
            default = "'[]'::jsonb"
        else:  # fall back to generic JSON representation
            column_type = "json"
            default = "'[]'"
        statements.append(
            f"ALTER TABLE {schema_editor.quote_name(table_name)} "
            f"ADD COLUMN {schema_editor.quote_name('placeholders')} {column_type} NOT NULL DEFAULT {default}"
        )

    if statements:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


def noop_reverse(apps, schema_editor):
    """Schema repair is irreversible."""


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_clause_template_columns, noop_reverse),
    ]
