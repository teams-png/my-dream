"""PRICING_REGION picks the price list a site sells: BookPilot sells the India list (INR), Ledgo the Global one (QAR)."""
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.pricing import addons, ensure_default_plans, plans_for, region_for

pytestmark = pytest.mark.django_db


@override_settings(PRICING_REGION="India")
def test_india_site_sells_the_inr_list_to_every_country():
    ensure_default_plans()
    assert region_for("Qatar") == region_for("India") == "India"
    prices = {p.max_users: (p.price, p.currency) for p in plans_for("Qatar", "boutique")}
    assert prices == {1: (Decimal("3999"), "INR"), 3: (Decimal("5999"), "INR"), 5: (Decimal("6999"), "INR")}
    five = plans_for("India", "supermarket").get(max_users=5)
    assert five.extra_user_price == Decimal("1000") and five.extra_branch_price == Decimal("1000")


@override_settings(PRICING_REGION="India")
def test_india_landing_and_signup_show_rupees(client):
    ensure_default_plans()
    landing = client.get("/")
    data = landing.context["pricing"]
    assert data["region"] == "India" and data["currency"] == "INR"
    assert {p["region"] for p in data["plans"]} == {"India"}
    assert data["website"]["India"] == {"website": 3999, "shop": 6999}
    assert b"INR 0" in landing.content
    signup = client.get(reverse("webapp:signup"))
    assert signup.context["form"].initial["country"] == "India"


@override_settings(PRICING_REGION="Global")
def test_global_site_sells_the_qar_list():
    ensure_default_plans()
    assert {p.currency for p in plans_for("India", "boutique")} == {"QAR"}


@override_settings(PRICING_REGION="India")
def test_customer_on_a_qar_plan_keeps_qar_plans_on_billing(client, tenant_a, tenant_a_owner):
    ensure_default_plans()
    qar = SubscriptionPlan.objects.filter(country="Global", tier="standard", max_users=3).first()
    sub = tenant_a.subscription
    sub.plan = qar
    sub.save()
    client.force_login(tenant_a_owner)
    page = client.get(reverse("webapp:billing"))
    assert {p.currency for p, _est in page.context["available_plans"]} == {"QAR"}
    assert addons(sub)["currency"] == "QAR"


def test_migration_brings_the_india_list_back():
    india = SubscriptionPlan.objects.filter(country="India", is_active=True)
    if india.exists():  # made by the 0015 migration on databases that ran it
        assert {p.price for p in india.filter(tier="standard")} == {Decimal("3999"), Decimal("5999"), Decimal("6999")}
