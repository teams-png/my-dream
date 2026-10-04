"""Quick sale counter: tap items, change the rate, add an item that isn't on the menu, take the money."""
import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.inventory.models import Product
from apps.tenants.models import Company
from apps.verticals.restaurant import starter_kit
from apps.verticals.restaurant.models import RestaurantMenuItem, RestaurantOrder

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))


def _signup(code, email):
    client = Client(REMOTE_ADDR=f"10.13.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    return company, client


@pytest.fixture
def counter():
    cache.clear()
    call_command("seed_platform")
    company, client = _signup("restaurant", "q1@t.qa")
    starter_kit.install(company, company.memberships.get(role__name="Owner").user, staff=False, expenses=False)
    return company, client


def _sell(client, lines, method="cash"):
    return client.post(reverse("webapp:restaurant_quick_sale_submit"), json.dumps({"method": method, "lines": lines}),
                       content_type="application/json")


def test_chaya_porotta_juice_and_a_cake(counter):
    company, client = counter
    page = client.get(reverse("webapp:restaurant_quick_sale")).content.decode()
    assert "Chaya (Kerala Tea)" in page and "qs-menu" in page
    chaya = Product.objects.for_company(company).get(sku="KL-chaya")
    porotta = Product.objects.for_company(company).get(sku="KL-kerala-porotta")
    juice = Product.objects.for_company(company).get(sku="KL-lime-juice")
    response = _sell(client, [{"product": chaya.id, "qty": 1, "price": "1.50"},
                              {"product": porotta.id, "qty": 2, "price": "1.50"},
                              {"product": juice.id, "qty": 1, "price": "5"},  # rate changed by hand (menu: 6)
                              {"name": "Cake slice", "qty": 1, "price": "4"}])
    data = response.json()
    assert response.status_code == 200 and data["ok"] and data["total"] == "13.50"
    order = RestaurantOrder.objects.for_company(company).get(order_number=data["number"])
    assert order.status == "paid" and order.channel == "takeaway" and order.invoice.amount_paid == Decimal("13.50")
    assert sorted((l.product.name, str(l.unit_price)) for l in order.lines.select_related("product")) == sorted([
        ("Chaya (Kerala Tea)", "1.50"), ("Kerala Porotta", "1.50"), ("Fresh Lime Juice", "5.00"), ("Cake slice", "4.00")])
    assert data["today_count"] == 1 and data["today_total"] == "13.50"
    # the same extra item name is re-used next time
    _sell(client, [{"name": "cake slice", "qty": 2, "price": "4"}], method="card")
    assert Product.objects.for_company(company).filter(sku__startswith="QUICK-").count() == 1


def test_bad_sales_are_refused(counter):
    company, client = counter
    assert _sell(client, []).json()["ok"] is False
    assert _sell(client, [{"name": "", "qty": 1, "price": "2"}]).status_code == 400
    assert _sell(client, [{"name": "Tea", "qty": 1, "price": "-2"}]).status_code == 400
    assert _sell(client, [{"name": "Tea", "qty": 1, "price": "2"}], method="bitcoin").status_code == 400
    other, _c = _signup("restaurant", "q2@t.qa")
    foreign = Product.objects.create(company=other, sku="X1", name="Other's tea", selling_price=1,
                                     unit=Product.objects.for_company(company).first().unit)
    assert _sell(client, [{"product": foreign.id, "qty": 1, "price": "1"}]).status_code == 400
    assert not RestaurantOrder.objects.for_company(company).filter(status="paid").exists()


def test_pin_quick_tiles(counter):
    company, client = counter
    item = RestaurantMenuItem.objects.for_company(company).get(product__sku="KL-thalassery-chicken-biryani")
    assert not item.is_quick
    assert client.post(reverse("webapp:restaurant_quick_sale_pin"), {"product": item.product_id}).json()["quick"] is True
    item.refresh_from_db()
    assert item.is_quick
    assert RestaurantMenuItem.objects.for_company(company).get(product__sku="KL-chaya").is_quick
