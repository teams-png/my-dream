"""Landing page: the India (INR) price list is retired; everyone sees the QAR prices."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.subscriptions.models import SubscriptionPlan

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_plans():
    SubscriptionPlan.objects.create(name="Global 3", country="Global", currency="QAR", price=Decimal("899"),
                                    max_users=3, is_active=True)
    # an old India plan left active in a database: still never shown
    SubscriptionPlan.objects.create(name="India 3", country="India", currency="INR", price=Decimal("7777"),
                                    max_users=3, is_active=True)


def _page(**headers):
    return Client().get(reverse("webapp:landing"), **headers).content.decode()


@pytest.mark.parametrize("headers", [{}, {"HTTP_CF_IPCOUNTRY": "QA"}, {"HTTP_CF_IPCOUNTRY": "IN"}])
def test_no_india_prices_for_anyone(two_plans, headers):
    page = _page(**headers)
    assert "899" in page and "7777" not in page and '"region": "India"' not in page and "Kolkata" not in page


def test_old_india_plans_are_switched_off_by_the_migration():
    from importlib import import_module
    from django.apps import apps as django_apps
    SubscriptionPlan.objects.create(name="India 1", country="India", currency="INR", price=Decimal("3999"), max_users=1)
    SubscriptionPlan.objects.create(name="Business 5", country="Global", currency="QAR", price=Decimal("899"),
                                    max_users=5, tier="standard", billing_period="yearly")
    import_module("apps.subscriptions.migrations.0013_new_prices_no_india").set_prices(django_apps, None)
    assert not SubscriptionPlan.objects.get(name="India 1").is_active
    assert SubscriptionPlan.objects.get(name="Business 5").price == Decimal("999")
