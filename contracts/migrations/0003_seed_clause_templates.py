from __future__ import annotations

from django.db import migrations

from contracts.data import CLAUSE_TEMPLATE_FIXTURES


def seed_clauses(apps, _schema_editor):
    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    for fixture in CLAUSE_TEMPLATE_FIXTURES:
        ClauseTemplate.objects.update_or_create(
            id=fixture["uuid"],
            defaults={
                "category": fixture["category"],
                "title": fixture["title"],
                "content": fixture["content"],
                "placeholders": fixture["placeholders"],
                "is_mandatory": fixture["is_mandatory"],
                "version": fixture["version"],
                "is_active": True,
            },
        )


def unseed_clauses(apps, _schema_editor):
    ClauseTemplate = apps.get_model("contracts", "ClauseTemplate")
    ids = [fixture["uuid"] for fixture in CLAUSE_TEMPLATE_FIXTURES]
    ClauseTemplate.objects.filter(id__in=ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0002_repair_clausetemplate_schema"),
    ]

    operations = [migrations.RunPython(seed_clauses, unseed_clauses)]
