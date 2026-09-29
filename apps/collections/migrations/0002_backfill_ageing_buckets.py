"""
Phase 30: seed_default_ageing_buckets() is only called for companies
created via create_company_with_owner() (i.e. new signups). Existing
companies get the standard 0-30 / 31-60 / 61-90 / 90+ buckets backfilled
here so AR/AP ageing works immediately without a manual setup step.

Idempotent (get_or_create).
"""
from django.db import migrations


DEFAULT_AGEING_BUCKETS = [
    ("0-30", 0, 30, 1),
    ("31-60", 31, 60, 2),
    ("61-90", 61, 90, 3),
    ("90+", 91, None, 4),
]


def backfill_buckets(apps, schema_editor):
    Company = apps.get_model("tenants", "Company")
    AgeingBucket = apps.get_model("collections", "AgeingBucket")

    for company in Company.objects.all():
        for label, min_days, max_days, order in DEFAULT_AGEING_BUCKETS:
            AgeingBucket.objects.get_or_create(
                company=company, label=label,
                defaults={"min_days": min_days, "max_days": max_days, "order": order},
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('collections', '0001_initial'),
        ('tenants', '0006_backfill_collections_permissions'),
    ]

    operations = [
        migrations.RunPython(backfill_buckets, noop_reverse),
    ]
