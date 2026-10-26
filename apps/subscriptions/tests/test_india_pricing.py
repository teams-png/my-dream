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
    assert prices == {1: (Decimal("4999"), "INR"), 3: (Decimal("7999"), "INR"), 5: (Decimal("10999"), "INR")}
    five = plans_for("India", "supermarket").get(max_users=5)
    assert five.extra_user_price == Decimal("2000") and five.extra_branch_price == Decimal("2500")


@override_settings(PRICING_REGION="India")
def test_india_landing_and_signup_show_rupees(client):
    ensure_default_plans()
    landing = client.get("/")
    data = landing.context["pricing"]
    assert data["region"] == "India" and data["currency"] == "INR"
    assert {p["region"] for p in data["plans"]} == {"India"}
    assert data["website"]["India"] == {"website": 4999, "shop": 9999}
    assert b"INR 0" in landing.content and data["tax"] == {"percent": "18", "label": "GST"}
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


def test_migrations_sell_the_new_india_prices_and_keep_old_plans():
    india = SubscriptionPlan.objects.filter(country="India")
    if india.exists():  # made by the 0015 and 0016 migrations on databases that ran them
        active = india.filter(tier="standard", is_active=True)
        assert {p.price for p in active} == {Decimal("4999"), Decimal("7999"), Decimal("10999")}
        old = india.filter(tier="standard", is_active=False, price=Decimal("5999")).first()
        assert old is not None and old.modules.count() == active.get(max_users=3).modules.count()


@override_settings(PRICING_REGION="India", PLAN_TAX_PERCENT="18")
def test_gst_is_added_to_inr_plans_only(client, tenant_a):
    ensure_default_plans()
    sub = tenant_a.subscription
    sub.plan = plans_for("India", "boutique").get(max_users=3)
    sub.save()
    a = addons(sub)
    assert (a["subtotal"], a["tax"], a["total"]) == (Decimal("7999"), Decimal("1439.82"), Decimal("9438.82"))
    sub.plan = SubscriptionPlan.objects.filter(country="Global", tier="standard", max_users=3).first()
    sub.save()
    assert addons(sub)["tax"] == 0
