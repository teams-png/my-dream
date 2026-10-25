from decimal import Decimal

from django.db import migrations

# Yearly INR price by users, for normal businesses and large shops alike; add-ons per year.
PRICES = {1: Decimal("3999"), 3: Decimal("5999"), 5: Decimal("6999")}
EXTRA_USER, EXTRA_BRANCH = Decimal("1000"), Decimal("1000")
TIER_LABEL = {"standard": "Business", "large": "Large Shop"}


def india_prices(apps, schema_editor):
    """The India (INR) price list is back: 1 user ₹3,999, 3 users ₹5,999, 5 users ₹6,999 a year. Old India plans
    are switched on again at the new prices; missing ones are made with the modules of the matching QAR plan.
    QAR plans are left as they are, so customers already paying in QAR keep their plan."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    for tier in ("standard", "large"):
        for users, price in PRICES.items():
            match = dict(country="India", currency="INR", billing_period="yearly", tier=tier, max_users=users)
            values = dict(price=price, is_active=True, extra_branch_price=EXTRA_BRANCH,
                          extra_user_price=EXTRA_USER if users == max(PRICES) else Decimal("0"),
                          name=f"{TIER_LABEL[tier]} · {users} user{'s' if users > 1 else ''}")
            plans = Plan.objects.filter(**match).exclude(name="Starter", price=0)
            if plans.exists():
                plans.update(**values)
                continue
            plan = Plan.objects.create(**match, **values)
            twin = Plan.objects.filter(country="Global", tier=tier, max_users=users, billing_period="yearly").first()
            if twin:
                plan.modules.set(twin.modules.all())


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0014_branch_price_300")]
    operations = [migrations.RunPython(india_prices, migrations.RunPython.noop)]
