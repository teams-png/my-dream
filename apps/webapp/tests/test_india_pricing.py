"""Landing page: India (INR) prices are for visitors from India only."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.subscriptions.models import SubscriptionPlan

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_plans():
    SubscriptionPlan.objects.create(name="Global 3", country="Global", currency="QAR", price=Decimal("999"),
                                    max_users=3, is_active=True)
    SubscriptionPlan.objects.create(name="India 3", country="India", currency="INR", price=Decimal("7777"),
                                    max_users=3, is_active=True)


def _page(**headers):
    return Client().get(reverse("webapp:landing"), **headers).content.decode()


def test_known_foreign_visitor_gets_no_india_prices(two_plans):
    page = _page(HTTP_CF_IPCOUNTRY="QA")
    assert "999" in page and "7777" not in page and '"visitor": "QA"' in page


def test_visitor_from_india_gets_india_prices(two_plans):
    page = _page(HTTP_CF_IPCOUNTRY="IN")
    assert "7777" in page and '"visitor": "IN"' in page


def test_unknown_country_is_left_to_the_browser_time_zone(two_plans):
    page = _page()
    assert '"visitor": ""' in page and "Asia\\/(Kolkata|Calcutta)" in page
    # the no-script list never shows India prices to someone we can't place
    assert "India 3 (India)" not in page
