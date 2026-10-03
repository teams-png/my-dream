from decimal import Decimal

from django.db import migrations


def set_prices(apps, schema_editor):
    """QAR plans: QAR 100 a year per branch above the first, and per user above 5 on the 5-user plans."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    for plan in Plan.objects.filter(country="Global", currency="QAR", billing_period="yearly"):
        changed = []
        if not plan.extra_branch_price:
            plan.extra_branch_price = Decimal("100")
            changed.append("extra_branch_price")
        if plan.max_users >= 5 and not plan.extra_user_price:
            plan.extra_user_price = Decimal("100")
            changed.append("extra_user_price")
        if changed:
            plan.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0008_plan_addons")]
    operations = [migrations.RunPython(set_prices, migrations.RunPython.noop)]
