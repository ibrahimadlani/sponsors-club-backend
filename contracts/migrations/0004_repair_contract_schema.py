
from __future__ import annotations

from django.db import migrations


def ensure_contract_columns(apps, schema_editor):
    """Backfill missing contract schema pieces for legacy databases."""

    Contract = apps.get_model("contracts", "Contract")
    table_name = Contract._meta.db_table
    connection = schema_editor.connection
    quote = schema_editor.quote_name

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
        existing_columns = {column.name for column in description}

    statements: list[str] = []

    def add_column(name: str, definition: str) -> None:
        statements.append(
            f"ALTER TABLE {quote(table_name)} ADD COLUMN {quote(name)} {definition}"
        )

    # Ensure title column exists for displaying contracts.
    if "title" not in existing_columns:
        default = "'Untitled contract'"
        if connection.vendor == "postgresql":
            default = "'Untitled contract'::text"
        add_column("title", f"varchar(255) NOT NULL DEFAULT {default}")

    # Align date columns with the new naming convention while preserving data.
    if "effective_date" not in existing_columns:
        if "start_date" in existing_columns:
            statements.append(
                f"ALTER TABLE {quote(table_name)} RENAME COLUMN {quote('start_date')} TO {quote('effective_date')}"
            )
        else:
            add_column("effective_date", "date NULL")

    if "expiration_date" not in existing_columns:
        if "end_date" in existing_columns:
            statements.append(
                f"ALTER TABLE {quote(table_name)} RENAME COLUMN {quote('end_date')} TO {quote('expiration_date')}"
            )
        else:
            add_column("expiration_date", "date NULL")

    # Ensure the JSON context payload exists.
    if "context" not in existing_columns:
        if connection.vendor == "sqlite":
            column_type = "text"
            default = "'{}'"
        elif connection.vendor == "postgresql":
            column_type = "jsonb"
            default = "'{}'::jsonb"
        else:
            column_type = "json"
            default = "'{}'"
        add_column("context", f"{column_type} NOT NULL DEFAULT {default}")

    # Rename the initiator foreign key if it still uses the legacy naming.
    if "initiated_by_id" not in existing_columns and "created_by_id" in existing_columns:
        statements.append(
            f"ALTER TABLE {quote(table_name)} RENAME COLUMN {quote('created_by_id')} TO {quote('initiated_by_id')}"
        )
    elif "initiated_by_id" not in existing_columns:
        if connection.vendor == "sqlite":
            column_type = "char(32)"
        elif connection.vendor == "postgresql":
            column_type = "uuid"
        else:
            column_type = "char(32)"
        add_column("initiated_by_id", f"{column_type} NULL")

    # Ensure the agent foreign key exists – legacy databases referenced athletes instead.
    if "agent_id" not in existing_columns:
        if connection.vendor == "sqlite":
            column_type = "char(32)"
        elif connection.vendor == "postgresql":
            column_type = "uuid"
        else:
            column_type = "char(32)"
        add_column("agent_id", f"{column_type} NULL")

    # Apply all of the collected statements in order.
    if statements:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    # Normalise legacy status values to the new lowercase vocabulary.
    status_mapping = {
        "DRAFT": "draft",
        "AGREEMENT": "agreement",
        "VERIFICATION": "negotiation",
        "ACTIVE": "active",
        "TERMINATED": "terminated",
    }

    with connection.cursor() as cursor:
        for legacy, current in status_mapping.items():
            cursor.execute(
                f"UPDATE {quote(table_name)} SET {quote('status')} = %s WHERE {quote('status')} = %s",
                [current, legacy],
            )


def noop_reverse(apps, schema_editor):
    """Schema repair is irreversible."""


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0003_seed_clause_templates"),
    ]

    operations = [
        migrations.RunPython(ensure_contract_columns, noop_reverse),
    ]
