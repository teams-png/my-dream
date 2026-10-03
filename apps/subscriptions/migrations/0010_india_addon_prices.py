from decimal import Decimal

from django.db import migrations


def set_prices(apps, schema_editor):
    """INR plans: INR 1,000 a year per branch above the first, and per user above 5 on the 5-user plans
    (same ratio as the plan prices: QAR 899 = INR 8,999)."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    for plan in Plan.objects.filter(country="India", currency="INR", billing_period="yearly"):
        changed = []
        if not plan.extra_branch_price:
            plan.extra_branch_price = Decimal("1000")
            changed.append("extra_branch_price")
        if plan.max_users >= 5 and not plan.extra_user_price:
            plan.extra_user_price = Decimal("1000")
            changed.append("extra_user_price")
        if changed:
            plan.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0009_plan_addon_prices")]
    operations = [migrations.RunPython(set_prices, migrations.RunPython.noop)]
