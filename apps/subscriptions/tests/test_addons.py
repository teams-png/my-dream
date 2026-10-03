"""Yearly add-ons: QAR 100 per user above 5 (on the 5-user plan) and per branch above the first."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.inventory.models import Warehouse
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.pricing import addons, amount_due, ensure_default_plans
from apps.tenants.models import Role
from apps.tenants.services import invite_member

pytestmark = pytest.mark.django_db


@pytest.fixture
def plans():
    from apps.subscriptions.pricing import plan_name
    ensure_default_plans()
    q = SubscriptionPlan.objects.filter(country="Global", tier="standard", currency="QAR")
    return {n: q.get(name=plan_name("standard", n)) for n in (1, 3, 5)}


def _users(company, n, start=0):
    staff = Role.objects.get(company=company, name="Staff")
    for i in range(start, start + n):
        u = get_user_model().objects.create_user(username=f"u{company.pk}-{i}", email=f"u{company.pk}-{i}@t.qa", password="Pass-12345!")
        invite_member(company=company, user=u, role=staff)


def test_new_plans_have_the_addon_prices(plans):
    assert plans[5].extra_user_price == Decimal("100") and plans[3].extra_user_price == 0
    assert all(p.extra_branch_price == Decimal("100") for p in plans.values())
    assert not SubscriptionPlan.objects.filter(country="India", currency="INR").exclude(extra_user_price=0).exists()


def test_extra_users_and_branches_are_charged(tenant_a, plans):
    sub = tenant_a.subscription
    sub.plan = plans[5]
    sub.save()
    _users(tenant_a, 6)  # owner + 6 = 7 users -> 2 extra
    for name in ("Mall", "Airport"):
        Warehouse.objects.create(company=tenant_a, name=name, is_active=True)
    branches = Warehouse.objects.for_company(tenant_a).filter(is_active=True).count()
    a = addons(sub)
    assert a["users"] == 7 and a["extra_users"] == 2 and a["users_amount"] == Decimal("200")
    assert a["extra_branches"] == branches - 1 and a["branches_amount"] == Decimal(100 * (branches - 1))
    assert amount_due(sub) == Decimal("899") + Decimal("200") + Decimal(100 * (branches - 1))


def test_three_user_plan_still_needs_an_upgrade(tenant_a, plans):
    sub = tenant_a.subscription
    sub.plan = plans[3]
    sub.save()
    _users(tenant_a, 2)
    with pytest.raises(ValueError):
        _users(tenant_a, 1, start=10)


def test_billing_page_and_landing_show_addons(client, tenant_a, tenant_a_owner, plans):
    sub = tenant_a.subscription
    sub.plan = plans[5]
    sub.save()
    for name in ("Main", "Second"):
        Warehouse.objects.create(company=tenant_a, name=name, is_active=True)
    client.force_login(tenant_a_owner)
    page = client.get(reverse("webapp:billing"))
    assert page.context["addons"]["extra_branches"] >= 1
    assert page.context["form"].initial["amount"] == amount_due(sub)
    client.logout()
    landing = client.get("/")
    data = landing.context["pricing"]["plans"]
    five = next(p for p in data if p["region"] == "Global" and p["tier"] == "standard" and p["users"] == 5)
    assert five["extra_user"] == "100" and five["extra_branch"] == "100"
