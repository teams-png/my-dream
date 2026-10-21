from decimal import Decimal

from django.db import migrations


def set_prices(apps, schema_editor):
    """Each branch above the first now costs QAR 300 a year (was QAR 100)."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    Plan.objects.filter(country="Global", currency="QAR", billing_period="yearly",
                        extra_branch_price__gt=0).update(extra_branch_price=Decimal("300"))


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0013_new_prices_no_india")]
    operations = [migrations.RunPython(set_prices, migrations.RunPython.noop)]
