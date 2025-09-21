from django.db import migrations, models


def add_is_mandatory_field(apps, schema_editor):
    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    table_name = ClauseTemplate._meta.db_table
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if "is_mandatory" in existing_columns:
        return

    field = models.BooleanField(default=False)
    field.set_attributes_from_name("is_mandatory")
    schema_editor.add_field(ClauseTemplate, field)


def remove_is_mandatory_field(apps, schema_editor):
    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    table_name = ClauseTemplate._meta.db_table
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if "is_mandatory" not in existing_columns:
        return

    field = ClauseTemplate._meta.get_field("is_mandatory")
    schema_editor.remove_field(ClauseTemplate, field)


class Migration(migrations.Migration):

    dependencies = [
        (
            "contracts",
            "0002_rename_contracts_c_organis_09059c_idx_contract_org_status_idx_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(add_is_mandatory_field, remove_is_mandatory_field),
    ]
