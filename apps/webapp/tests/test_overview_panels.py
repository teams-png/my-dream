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


def test_overview_title_is_clean():
    import re
    _company, _user, c = _business("perfume_shop")
    page = c.get(reverse("webapp:dashboard")).content.decode()
    title = re.search(r"<title>(.*?)</title>", page, re.S).group(1)
    assert "<script" not in title and "Overview" in title
    assert page.count("digital clock") == 1


def test_variant_parents_never_show_as_out_of_stock():
    from django.test import override_settings
    from apps.industry import sample_kit
    from apps.inventory.models import Product
    company, user, c = _business("sports_shop")
    with override_settings(SAMPLE_DATA_KIT=True):
        sample_kit.install(company, user)
    parent = Product.objects.filter(company=company, variants__isnull=False).distinct().first()
    assert parent and not parent.is_stock_tracked
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Out of stock" not in page
    listing = c.get(reverse("webapp:sports_product_list")).content.decode()
    assert "Red / S" in listing or "S" in listing
    from apps.inventory.pictures import pick
    assert pick("Football jersey") == "tshirt" and pick("Charging port (Samsung A-series)") == "charger"


def test_perfume_and_protein_forms_have_their_own_examples():
    _company, _user, c = _business("perfume_shop")
    page = c.get(reverse("webapp:product_add")).content.decode()
    assert "Keratin" not in page and "Oud Royal" in page


def test_sports_products_use_the_full_form_and_keep_sport_and_gender():
    from apps.inventory.models import Product, Unit
    company, _user, c = _business("sports_shop")
    assert c.get(reverse("webapp:sports_product_add")).url == reverse("webapp:product_add")
    form = c.get(reverse("webapp:product_add")).content.decode()
    assert 'name="sport_category"' in form and 'name="image"' in form
    unit = Unit.objects.create(company=company, name="pcs")
    r = c.post(reverse("webapp:product_add"), {"sku": "BAT-9", "name": "Kashmir willow bat", "unit": unit.id,
                                               "cost_price": "80", "selling_price": "140", "reorder_level": "1",
                                               "is_stock_tracked": "on", "sport_category": "cricket", "gender": "kids"})
    assert r.status_code == 302, r.content.decode()[:2000]
    bat = Product.objects.get(company=company, sku="BAT-9")
    assert bat.sports_detail.sport_category == "cricket" and bat.sports_detail.gender == "kids"
    listing = c.get(reverse("webapp:sports_product_list")).content.decode()
    assert "Kashmir willow bat" in listing and "Cricket" in listing and "Kids" in listing
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert reverse("webapp:retail_reports") in page and reverse("webapp:retail_sale_list") in page


def test_team_order_with_players_print_sheet_and_status():
    from apps.verticals.sports_shop.models import TeamOrder
    from apps.webapp.team_order_views import parse_players
    assert parse_players("Rahul, 7, m\n\nAhmed\t10\tL\n,9") == [("Rahul", "7", "M"), ("Ahmed", "10", "L"), ("", "9", "")]
    company, _user, c = _business("sports_shop")
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert reverse("webapp:team_order_list") in page
    r = c.post(reverse("webapp:team_order_add"), {"team_name": "Doha Strikers", "item": "Home jersey", "price_per_piece": "60",
                                                  "advance": "100", "due_date": "2030-01-10",
                                                  "players": "Rahul, 7, M\nAhmed, 10, L\nJoseph, 1, M"})
    assert r.status_code == 302, r.content.decode()[:1500]
    order = TeamOrder.objects.get(company=company)
    assert order.pieces == 3 and order.total == 180 and order.balance == 80
    detail = c.get(r.url).content.decode()
    assert "RAHUL" in detail and "M × 2" in detail
    c.post(r.url, {"status": "printing"})
    order.refresh_from_db()
    assert order.status == "printing"
    bad = c.post(reverse("webapp:team_order_add"), {"team_name": "X", "item": "Y", "due_date": "2030-01-10", "players": ""})
    assert bad.status_code == 200 and "at least one player" in bad.content.decode()
    other, _u, oc = _business("perfume_shop")
    assert oc.get(reverse("webapp:team_order_list")).status_code == 404
