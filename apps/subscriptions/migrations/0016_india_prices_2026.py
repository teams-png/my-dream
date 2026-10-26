from decimal import Decimal

from django.db import migrations

# New yearly INR prices (before GST): 1 user ₹4,999, 3 users ₹7,999, 5 users ₹10,999; extra user ₹2,000 (5-user
# plan), extra branch ₹2,500.
PRICES = {1: Decimal("4999"), 3: Decimal("7999"), 5: Decimal("10999")}
EXTRA_USER, EXTRA_BRANCH = Decimal("2000"), Decimal("2500")
TIER_LABEL = {"standard": "Business", "large": "Large Shop"}


def new_prices(apps, schema_editor):
    """Customers already on an India plan keep it at the price they pay: those plans are only switched off for new
    sign-ups. New plans at the new prices (same modules) are what new customers and plan changes get."""
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    for tier in ("standard", "large"):
        for users, price in PRICES.items():
            match = dict(country="India", currency="INR", billing_period="yearly", tier=tier, max_users=users)
            values = dict(extra_branch_price=EXTRA_BRANCH,
                          extra_user_price=EXTRA_USER if users == max(PRICES) else Decimal("0"))
            current = Plan.objects.filter(**match, price=price).exclude(name="Starter", price=0).first()
            if current:  # already there (e.g. the migration ran on a fresh database seeded with these prices)
                Plan.objects.filter(pk=current.pk).update(is_active=True, **values)
                continue
            old = list(Plan.objects.filter(**match, is_active=True).exclude(name="Starter", price=0))
            plan = Plan.objects.create(name=f"{TIER_LABEL[tier]} · {users} user{'s' if users > 1 else ''}", price=price,
                                       is_active=True, **match, **values)
            twin = old[0] if old else Plan.objects.filter(country="Global", tier=tier, max_users=users,
                                                         billing_period="yearly").first()
            if twin:
                plan.modules.set(twin.modules.all())
            Plan.objects.filter(pk__in=[p.pk for p in old]).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0015_india_price_list")]
    operations = [migrations.RunPython(new_prices, migrations.RunPython.noop)]
