from decimal import Decimal

from django.db import migrations

# Yearly QAR price by users, for normal businesses and large shops alike.
PRICES = {1: Decimal("699"), 3: Decimal("899"), 5: Decimal("999")}


def set_prices(apps, schema_editor):
    """New yearly prices (1 user QAR 699, 3 users QAR 899, 5 users QAR 999) and no India / INR plans for new
    sign-ups. India plans are only switched off: companies already on one keep it until they change plan."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    Plan.objects.filter(country="India").update(is_active=False)
    for users, price in PRICES.items():
        Plan.objects.filter(country="Global", currency="QAR", billing_period="yearly", max_users=users,
                            tier__in=["standard", "large"]).update(price=price)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0012_trial_retention")]
    operations = [migrations.RunPython(set_prices, migrations.RunPython.noop)]
