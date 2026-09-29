from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.subscriptions import pricing
from apps.subscriptions.models import SubscriptionPlan
from apps.tenants.models import Company, CompanyMembership

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def _prices(country, business_type):
    return [(p.max_users, p.currency, p.price) for p in pricing.plans_for(country, business_type)]


def test_seeded_price_table():
    assert _prices("Qatar", "restaurant") == [(1, "QAR", 399), (3, "QAR", 699), (5, "QAR", 899)]
    assert _prices("Qatar", "supermarket") == [(1, "QAR", 499), (3, "QAR", 899), (5, "QAR", 1199)]
    assert _prices("India", "clothing_store") == [(1, "INR", 3999), (3, "INR", 6999), (5, "INR", 8999)]
    assert _prices("India", "wholesale_business") == [(1, "INR", 5999), (3, "INR", 9999), (5, "INR", 13999)]
    # every other country uses the QAR (international) price list
    for country in ("United Arab Emirates", "Saudi Arabia", "United Kingdom", "United States", "Germany", "Other"):
        assert _prices(country, "restaurant") == _prices("Qatar", "restaurant")
    assert not SubscriptionPlan.objects.filter(name="Starter", is_active=True).exists()


def test_seeding_is_idempotent_and_keeps_admin_prices():
    plan = pricing.plans_for("Qatar", "restaurant").first()
    plan.price = Decimal("350")
    plan.save()
    call_command("seed_platform")
    assert SubscriptionPlan.objects.filter(is_active=True).count() == 12
    plan.refresh_from_db()
    assert plan.price == Decimal("350")


def test_old_free_starter_plan_is_not_reused():
    SubscriptionPlan.objects.all().delete()  # a database from before the price list
    SubscriptionPlan.objects.create(name="Starter", price=0, billing_period="yearly", max_users=5)
    call_command("seed_platform")
    assert _prices("Qatar", "restaurant") == [(1, "QAR", 399), (3, "QAR", 699), (5, "QAR", 899)]
    assert not SubscriptionPlan.objects.get(name="Starter").is_active


def test_local_estimate_is_display_only():
    assert pricing.local_estimate(399, "QAR", "AED") == Decimal("403")
    assert pricing.local_estimate(399, "QAR", "USD") == Decimal("110")
    assert pricing.local_estimate(399, "QAR", "QAR") is None
    assert pricing.local_estimate(3999, "INR", "USD") is None
    with override_settings(DISPLAY_FX_PER_QAR={"GBP": "0.20"}):
        assert pricing.local_estimate(899, "QAR", "GBP") == Decimal("180")


def _signup(client, **over):
    data = {"business_name": "Shop One", "business_type": "supermarket", "country": "India", "full_name": "A B",
            "email": "a@shop.test", "phone": "", "password": "Shop-One-2026!", "accept_terms": "on", "website": ""}
    data.update(over)
    client.post(reverse("webapp:signup"), data)
    return Company.objects.get(email=data["email"])


def test_signup_gets_region_and_tier_plan(client):
    company = _signup(client)
    plan = company.subscription.plan
    assert (plan.country, plan.tier, plan.max_users, plan.currency) == ("India", "large", 1, "INR")
    assert company.default_currency == "INR"


def test_signup_plan_from_other_region_is_swapped(client):
    india_3 = pricing.plans_for("India", "restaurant").get(max_users=3)
    company = _signup(client, business_type="restaurant", country="United Kingdom", email="uk@shop.test", plan=india_3.id)
    plan = company.subscription.plan
    assert (plan.country, plan.max_users, plan.currency, plan.price) == ("Global", 3, "QAR", 699)
    assert company.default_currency == "GBP"


def test_landing_and_signup_show_prices(client):
    for url in ("/", reverse("webapp:signup")):
        page = client.get(url)
        assert page.status_code == 200
        data = page.context["pricing"]
        assert len(data["plans"]) == 12 and "supermarket" in data["large_types"]


def test_owner_changes_plan_but_not_below_user_count(client):
    company = _signup(client, business_type="restaurant", country="Qatar", email="q@shop.test")
    five = pricing.plans_for("Qatar", "restaurant").get(max_users=5)
    one = pricing.plans_for("Qatar", "restaurant").get(max_users=1)
    client.post(reverse("webapp:billing"), {"change_plan": five.id})
    company.subscription.refresh_from_db()
    assert company.subscription.plan == five

    from django.contrib.auth import get_user_model
    from apps.tenants.models import Role
    helper = get_user_model().objects.create_user(username="h@shop.test", email="h@shop.test", password="x-Strong-123")
    CompanyMembership.objects.create(company=company, user=helper, role=Role.objects.get(company=company, name="Staff"))
    client.post(reverse("webapp:billing"), {"change_plan": one.id})
    company.subscription.refresh_from_db()
    assert company.subscription.plan == five  # 2 users can't fit a 1-user plan

    india = pricing.plans_for("India", "restaurant").first()
    client.post(reverse("webapp:billing"), {"change_plan": india.id})
    company.subscription.refresh_from_db()
    assert company.subscription.plan == five  # other region's price list is not selectable
