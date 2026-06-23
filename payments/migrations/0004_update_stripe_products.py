"""Assign Stripe product identifiers to seeded subscription plans."""

from django.db import migrations


def assign_products(apps, schema_editor):
    """Update seeded plans with Stripe product metadata."""

    del schema_editor

    subscription_plan = apps.get_model("payments", "SubscriptionPlan")

    updates = {
        "agent-pro": {
            "stripe_product_id": "prod_T5gH4ncHV8mMUD",
        },
        "agent-agency": {
            "stripe_product_id": "prod_T5gKJ1fS6JFZVm",
        },
        "org-pro": {
            "stripe_product_id": "prod_T5gLLMUGNmVWhm",
        },
        "org-enterprise": {
            "name": "Organisation Entreprise",
            "stripe_product_id": "prod_T5gNw4B5R8lcmF",
        },
    }

    for code, fields in updates.items():
        subscription_plan.objects.filter(code=code).update(**fields)


def remove_products(apps, schema_editor):
    """Rollback helper removing Stripe metadata from plans."""

    del schema_editor

    subscription_plan = apps.get_model("payments", "SubscriptionPlan")

    revert = {
        "agent-pro": {
            "stripe_product_id": "",
        },
        "agent-agency": {
            "stripe_product_id": "",
        },
        "org-pro": {
            "stripe_product_id": "",
        },
        "org-enterprise": {
            "name": "Organisation Enterprise",
            "stripe_product_id": "",
        },
    }

    for code, fields in revert.items():
        subscription_plan.objects.filter(code=code).update(**fields)


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_seed_subscription_plans"),
    ]

    operations = [
        migrations.RunPython(assign_products, remove_products),
    ]
