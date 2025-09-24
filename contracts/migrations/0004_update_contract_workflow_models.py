"""Align the legacy contracts schema with the new workflow models."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def map_clause_categories(apps, schema_editor):
    """Map the former template type to the new category choice."""

    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")

    type_to_category = {
        "obligation": "obligations",
        "condition": "administrative",
        "paiement": "finance",
        "duree": "administrative",
        "legal": "ethics",
    }

    for template in ClauseTemplate.objects.all():
        legacy_type = getattr(template, "type", None)
        template.category = type_to_category.get(legacy_type, "obligations")
        template.save(update_fields=["category"])


def normalise_contract_statuses(apps, schema_editor):
    """Convert historical status values to the new lowercase choices."""

    Contract = apps.get_model("contracts", "Contract")

    mapping = {
        "DRAFT": "draft",
        "NEGOTIATION": "negotiation",
        "AGREEMENT": "agreement",
        "VERIFICATION": "negotiation",
        "ACTIVE": "active",
        "TERMINATED": "terminated",
    }

    for contract in Contract.objects.all():
        contract.status = mapping.get(contract.status, "draft")
        contract.save(update_fields=["status"])


def ensure_contract_agents(apps, schema_editor):
    """Guarantee that every contract is linked to an agent profile."""

    Contract = apps.get_model("contracts", "Contract")
    AgentProfile = apps.get_model("users", "AgentProfile")
    User = apps.get_model("users", "User")

    agent = AgentProfile.objects.first()
    if agent is None:
        placeholder_user = User(
            email="placeholder-agent@sponsorsclub.local",
            account_type="AGENT",
            is_active=True,
        )
        if hasattr(placeholder_user, "set_password"):
            placeholder_user.set_password("placeholder")
        placeholder_user.save()
        agent = AgentProfile.objects.create(
            user=placeholder_user,
            display_name="Default Agent",
        )

    Contract.objects.filter(agent__isnull=True).update(agent=agent)


def seed_clause_defaults(apps, schema_editor):
    """Populate the new clause columns using existing template information."""

    ContractClause = apps.get_model("contracts", "ContractClause")

    for clause in ContractClause.objects.select_related("template"):
        template = clause.template
        if template:
            clause.title = template.title
            clause.content = template.content
            clause.is_mandatory = getattr(template, "is_mandatory", False)
        else:
            clause.title = clause.title or "Clause"
            clause.content = clause.content or ""
            clause.is_mandatory = False
        clause.is_modified = False
        clause.save(update_fields=["title", "content", "is_mandatory", "is_modified"])


def reconcile_is_mandatory_column(apps, schema_editor):
    """Rename or merge the legacy mandatory column with the new flag."""

    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    table_name = ClauseTemplate._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if "mandatory" not in existing_columns:
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_mandatory = schema_editor.quote_name("mandatory")
    quoted_is_mandatory = schema_editor.quote_name("is_mandatory")

    if "is_mandatory" not in existing_columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} RENAME COLUMN {quoted_mandatory} TO {quoted_is_mandatory}"
        )
        return

    schema_editor.execute(
        f"UPDATE {quoted_table} SET {quoted_is_mandatory} = {quoted_mandatory}"
    )
    schema_editor.execute(
        f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_mandatory}"
    )


def reverse_reconcile_is_mandatory_column(apps, schema_editor):
    """Restore the legacy mandatory column when rolling back the migration."""

    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    table_name = ClauseTemplate._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if "is_mandatory" not in existing_columns:
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_mandatory = schema_editor.quote_name("mandatory")
    quoted_is_mandatory = schema_editor.quote_name("is_mandatory")

    if "mandatory" in existing_columns:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET {quoted_mandatory} = {quoted_is_mandatory}"
        )
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_is_mandatory}"
        )
        return

    schema_editor.execute(
        f"ALTER TABLE {quoted_table} RENAME COLUMN {quoted_is_mandatory} TO {quoted_mandatory}"
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        (
            "contracts",
            "0003_ensure_is_mandatory_on_clausetemplate",
        ),
        ("users", "0005_remove_user_id_remove_user_username_and_more"),
        ("organisations", "0005_organisation_owner"),
    ]

    operations = [
        migrations.AddField(
            model_name="clausetemplate",
            name="category",
            field=models.CharField(
                choices=[
                    ("obligations", "Obligations"),
                    ("finance", "Finance"),
                    ("ip", "IP"),
                    ("ethics", "Ethics"),
                    ("confidentiality", "Confidentiality"),
                    ("termination", "Résiliation"),
                    ("administrative", "Administratives"),
                ],
                default="obligations",
                max_length=32,
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    reconcile_is_mandatory_column,
                    reverse_code=reverse_reconcile_is_mandatory_column,
                )
            ],
            state_operations=[
                migrations.RenameField(
                    model_name="clausetemplate",
                    old_name="mandatory",
                    new_name="is_mandatory",
                ),
            ],
        ),
        migrations.RunPython(map_clause_categories, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="clausetemplate",
            name="identifier",
        ),
        migrations.RemoveField(
            model_name="clausetemplate",
            name="is_active",
        ),
        migrations.RemoveField(
            model_name="clausetemplate",
            name="type",
        ),
        migrations.AlterField(
            model_name="clausetemplate",
            name="category",
            field=models.CharField(
                choices=[
                    ("obligations", "Obligations"),
                    ("finance", "Finance"),
                    ("ip", "IP"),
                    ("ethics", "Ethics"),
                    ("confidentiality", "Confidentiality"),
                    ("termination", "Résiliation"),
                    ("administrative", "Administratives"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="clausetemplate",
            name="content",
            field=models.TextField(
                help_text="Supports placeholders using double curly braces like {{athlete_name}}",
            ),
        ),
        migrations.AlterModelOptions(
            name="clausetemplate",
            options={"ordering": ("category", "title", "-version")},
        ),
        migrations.AlterUniqueTogether(
            name="clausetemplate",
            unique_together={("title", "version")},
        ),
        migrations.RemoveConstraint(
            model_name="contractclause",
            name="unique_contract_clause_order",
        ),
        migrations.RemoveField(
            model_name="contractclause",
            name="values",
        ),
        migrations.RemoveField(
            model_name="contractclause",
            name="order_index",
        ),
        migrations.AddField(
            model_name="contractclause",
            name="title",
            field=models.CharField(default="Clause", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="contractclause",
            name="content",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="contractclause",
            name="is_mandatory",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="contractclause",
            name="is_modified",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="contractclause",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_clauses",
                to="contracts.clausetemplate",
            ),
        ),
        migrations.AlterModelOptions(
            name="contractclause",
            options={"ordering": ("created_at",)},
        ),
        migrations.RunPython(seed_clause_defaults, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="contract",
            name="contract_org_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="contract",
            name="contract_athlete_idx",
        ),
        migrations.RemoveIndex(
            model_name="contract",
            name="contract_start_idx",
        ),
        migrations.RemoveField(
            model_name="contract",
            name="athlete",
        ),
        migrations.RemoveField(
            model_name="contract",
            name="amount",
        ),
        migrations.RemoveField(
            model_name="contract",
            name="currency",
        ),
        migrations.RenameField(
            model_name="contract",
            old_name="created_by",
            new_name="initiated_by",
        ),
        migrations.AlterField(
            model_name="contract",
            name="initiated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="initiated_contracts",
                to="organisations.collaborator",
            ),
        ),
        migrations.RenameField(
            model_name="contract",
            old_name="start_date",
            new_name="effective_date",
        ),
        migrations.RenameField(
            model_name="contract",
            old_name="end_date",
            new_name="expiration_date",
        ),
        migrations.AddField(
            model_name="contract",
            name="title",
            field=models.CharField(default="Untitled contract", max_length=255),
        ),
        migrations.AddField(
            model_name="contract",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contracts",
                to="users.agentprofile",
            ),
        ),
        migrations.AlterField(
            model_name="contract",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("negotiation", "Negotiation"),
                    ("agreement", "Agreement"),
                    ("active", "Active"),
                    ("terminated", "Terminated"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.RunPython(normalise_contract_statuses, migrations.RunPython.noop),
        migrations.RunPython(ensure_contract_agents, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contract",
            name="title",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="contract",
            name="agent",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contracts",
                to="users.agentprofile",
            ),
        ),
        migrations.AddIndex(
            model_name="contract",
            index=models.Index(
                fields=("organisation", "status"),
                name="contracts_org_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contract",
            index=models.Index(
                fields=("agent",),
                name="contracts_agent_idx",
            ),
        ),
        migrations.DeleteModel(
            name="ContractStatusHistory",
        ),
        migrations.DeleteModel(
            name="ContractVersion",
        ),
        migrations.CreateModel(
            name="ContractRevision",
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
                ("comment", models.TextField(blank=True)),
                (
                    "accepted",
                    models.BooleanField(blank=True, default=None, null=True),
                ),
                (
                    "contract",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="contracts.contract",
                    ),
                ),
                (
                    "proposed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ContractFile",
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
                ("pdf", models.FileField(upload_to="contracts/exports/")),
                (
                    "contract",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="file",
                        to="contracts.contract",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddField(
            model_name="contractrevision",
            name="clauses_changed",
            field=models.ManyToManyField(
                blank=True,
                related_name="revisions",
                to="contracts.contractclause",
            ),
        ),
    ]
