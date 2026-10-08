"""The overview opens on today's work for each kind of business: kitchen timers, low stock, and so on."""
import datetime

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


def _business(code):
    call_command("seed_platform")
    user = User.objects.create_user(username=f"o@{code}.test", email=f"o@{code}.test", password="Pass-2026-xyz!")
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=code.title(), slug=code.replace("_", "-"), business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    c = Client()
    c.force_login(user)
    return company, user, c


def test_restaurant_overview_has_kitchen_timers():
    from apps.verticals.restaurant import services as rs, starter_kit
    from apps.verticals.restaurant.models import DiningTable, KitchenTicket, RestaurantMenuItem
    company, user, c = _business("restaurant")
    starter_kit.install(company, user)
    item = RestaurantMenuItem.objects.filter(company=company).select_related("product").first()
    RestaurantMenuItem.objects.filter(pk=item.pk).update(preparation_minutes=7)
    order = rs.create_order(company=company, channel="dine_in", table=DiningTable.objects.filter(company=company).first())
    rs.add_order_line(company=company, order=order, product=item.product, quantity=2)
    rs.send_to_kitchen(company=company, order=order)
    ticket = KitchenTicket.objects.get(company=company)
    KitchenTicket.objects.filter(pk=ticket.pk).update(printed_at=timezone.now() - datetime.timedelta(minutes=9))

    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Kitchen timer" in page and ticket.ticket_number in page and 'data-target="7"' in page
    assert "1 late" in page  # 9 minutes against a 7 minute dish
    assert 'id="ovClock"' in page
    assert reverse("webapp:restaurant_kitchen") in page and reverse("webapp:restaurant_quick_sale") in page

    kds = c.get(reverse("webapp:restaurant_kitchen")).content.decode()
    assert 'data-target="7"' in kds


def test_shop_overview_lists_low_stock_and_best_sellers():
    from apps.inventory.models import Product, Unit
    company, user, c = _business("supermarket")
    Product.objects.create(company=company, sku="MILK-1", name="Fresh milk 1L", unit=Unit.objects.create(company=company, name="pcs"),
                           selling_price=6, cost_price=4, reorder_level=5, is_stock_tracked=True)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Running low" in page and "Fresh milk 1L" in page and "Out of stock" in page
    assert "Best sellers today" in page and "Business overview" not in page
