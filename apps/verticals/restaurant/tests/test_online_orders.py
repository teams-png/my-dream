"""Website ordering: the owner switches the cart on, customers order from the website, staff accept or reject."""
import io
import json
import zipfile
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from apps.industry import site_builder, website_kit
from apps.tenants.models import Company
from apps.verticals.restaurant.models import KitchenTicket, OnlineOrder, RestaurantMenuItem, RestaurantProfile

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clean_cache")]
_ips = iter(range(1, 250))
SETTINGS = {"web_orders_enabled": "on", "web_pickup": "on", "web_delivery": "on", "delivery_charge": "5",
            "delivery_minimum": "30", "web_ready_minutes": "25", "web_note": "Delivery only in Doha"}


@pytest.fixture
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(RESTAURANT_STARTER_KIT=True)
def _restaurant(email):
    client = Client(REMOTE_ADDR=f"10.9.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Resto {email}", "business_type": "restaurant", "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    return company, client, website_kit.kit_for(company)


def _item(company, sku):
    return RestaurantMenuItem.objects.for_company(company).select_related("product").get(product__sku=sku)


def _order(kit, ip="1.2.3.4", **data):
    body = {"name": "Ameen", "phone": "+974 5555 1234", "mode": "pickup", "items": [], **data}
    return Client(REMOTE_ADDR=ip).post(reverse("webapp:kit_order", args=[kit.public_id]), json.dumps(body),
                                       content_type="application/json", HTTP_ORIGIN="https://www.resto.qa")


def test_cart_is_off_until_the_owner_switches_it_on():
    company, owner, kit = _restaurant("o1@t.qa")
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    feed = Client().get(reverse("webapp:kit_catalogue", args=[kit.public_id])).json()
    assert feed["ordering"] == {"enabled": False} and not any(i["orderable"] for i in feed["items"])
    r = _order(kit, items=[{"id": biryani.product_id, "qty": 1}])
    assert r.status_code == 400 and "switched off" in r.json()["error"]
    assert "enabled\": false" in Client().get(reverse("webapp:kit_order_js", args=[kit.public_id])).content.decode()

    assert owner.get(reverse("webapp:restaurant_online_orders")).status_code == 200
    owner.post(reverse("webapp:restaurant_online_settings"), SETTINGS)
    cache.clear()
    feed = Client().get(reverse("webapp:kit_catalogue", args=[kit.public_id])).json()
    assert feed["ordering"]["enabled"] and feed["ordering"]["delivery_fee"] == "5.00"
    assert next(i for i in feed["items"] if i["id"] == biryani.product_id)["orderable"] is True
    js = Client().get(reverse("webapp:kit_order_js", args=[kit.public_id])).content.decode()
    assert reverse("webapp:kit_order", args=[kit.public_id]) in js and "Delivery only in Doha" in js


def test_pickup_order_uses_bookpilot_prices_and_staff_accept_it():
    company, owner, kit = _restaurant("o2@t.qa")
    owner.post(reverse("webapp:restaurant_online_settings"), SETTINGS)
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    r = _order(kit, items=[{"id": biryani.product_id, "qty": 2, "price": "0.01"}], note="Less spicy")
    assert r.status_code == 201, r.content
    data = r.json()
    online = OnlineOrder.objects.for_company(company).get()
    assert online.status == "new" and online.order.status == "held" and online.order.channel == "takeaway"
    assert online.total == biryani.product.selling_price * 2 and data["total"] == f"{online.total:.2f}"
    assert online.source == "www.resto.qa" and online.order.customer.phone == "+974 5555 1234"
    assert not KitchenTicket.objects.for_company(company).exists()

    assert owner.get(reverse("webapp:restaurant_online_waiting")).json() == {"enabled": True, "new": 1}
    page = owner.get(reverse("webapp:restaurant_online_orders")).content.decode()
    assert online.order.order_number in page and "Less spicy" in page
    track = Client().get(data["track_url"].split("testserver", 1)[-1]).content.decode()
    assert "confirm it shortly" in track

    owner.post(reverse("webapp:restaurant_online_action", args=[online.id]), {"do": "accept"})
    online.refresh_from_db(); online.order.refresh_from_db()
    assert online.status == "accepted" and online.order.status == "kitchen" and online.stage == "preparing"
    assert KitchenTicket.objects.for_company(company).filter(order=online.order).exists()
    assert "being prepared" in Client().get(data["track_url"].split("testserver", 1)[-1]).content.decode()
    assert owner.get(reverse("webapp:restaurant_online_waiting")).json()["new"] == 0


def test_delivery_fee_minimum_address_and_reject():
    company, owner, kit = _restaurant("o3@t.qa")
    owner.post(reverse("webapp:restaurant_online_settings"), SETTINGS)
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    one = [{"id": biryani.product_id, "qty": 1}]
    assert "address" in _order(kit, mode="delivery", address="", items=[{"id": biryani.product_id, "qty": 2}]).json()["error"]
    assert "minimum" in _order(kit, ip="1.1.1.2", mode="delivery", address="Zone 25, Street 9, Villa 4", items=one).json()["error"]
    r = _order(kit, ip="1.1.1.3", mode="delivery", address="Zone 25, Street 9, Villa 4", items=[{"id": biryani.product_id, "qty": 2}])
    assert r.status_code == 201
    online = OnlineOrder.objects.for_company(company).get()
    assert online.order.channel == "delivery" and online.total == biryani.product.selling_price * 2 + Decimal("5")
    fee_line = online.order.lines.get(product__sku="DELIVERY-FEE")
    assert fee_line.sent_at is not None  # never printed on the kitchen ticket

    owner.post(reverse("webapp:restaurant_online_action", args=[online.id]), {"do": "reject", "reason": "Too far"})
    online.refresh_from_db()
    assert online.status == "rejected" and online.order.status == "cancelled" and online.stage == "rejected"
    track = Client().get(r.json()["track_url"].split("testserver", 1)[-1]).content.decode()
    assert "could not take this order" in track and "Too far" in track


def test_sold_out_paused_honeypot_flood_and_other_shops_items():
    company, owner, kit = _restaurant("o4@t.qa")
    other, _o, _k = _restaurant("o5@t.qa")
    owner.post(reverse("webapp:restaurant_online_settings"), SETTINGS)
    dosa = _item(company, "KL-masala-dosa")
    RestaurantMenuItem.objects.filter(pk=dosa.pk).update(is_available=False)
    assert "not available" in _order(kit, items=[{"id": dosa.product_id, "qty": 1}]).json()["error"]
    foreign = _item(other, "KL-masala-dosa")
    assert "no longer on the menu" in _order(kit, ip="2.2.2.2", items=[{"id": foreign.product_id, "qty": 1}]).json()["error"]
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    assert _order(kit, ip="3.3.3.3", company_website="x", items=[{"id": biryani.product_id, "qty": 1}]).status_code == 201
    assert not OnlineOrder.objects.for_company(company).exists()
    for bad in ([{"id": biryani.product_id, "qty": 0}], [{"id": "x"}], ["junk"], "nope"):
        assert _order(kit, ip="4.4.4.4", items=bad).status_code in (400, 429)
    codes = [_order(kit, ip="5.5.5.5", items=[{"id": biryani.product_id, "qty": 1}]).status_code for _ in range(8)]
    assert codes[:6] == [201] * 6 and codes[-1] == 429

    RestaurantProfile.objects.filter(company=company).update(web_paused=True)
    assert "not taking" in _order(kit, ip="6.6.6.6", items=[{"id": biryani.product_id, "qty": 1}]).json()["error"]

    # staff of another restaurant cannot touch these orders
    online = OnlineOrder.objects.for_company(company).first()
    assert _o.post(reverse("webapp:restaurant_online_action", args=[online.id]), {"do": "accept"}).status_code == 404


def test_hosted_website_and_wordpress_plugin_show_the_cart():
    company, owner, kit = _restaurant("o6@t.qa")
    design = site_builder.design_for(company)
    design.enabled = design.published = True
    design.save()
    url = reverse("webapp:site_public", args=[kit.public_id])
    assert "data-bp-add" not in Client().get(url).content.decode()
    owner.post(reverse("webapp:restaurant_online_settings"), SETTINGS)
    cache.clear()
    page = Client().get(url).content.decode()
    assert "data-bp-add" in page and reverse("webapp:kit_order_js", args=[kit.public_id]) in page

    call_command("seed_platform")
    admin = get_user_model().objects.create_user(username="pa6", email="pa6@bp.qa", password="Pass-12345!", is_platform_admin=True)
    ac = Client()
    ac.force_login(admin)
    assert "Website ordering (cart)" in ac.get(reverse("webapp:kit_detail", args=[company.id])).content.decode()
    plugin = ac.get(reverse("webapp:kit_wp_plugin", args=[company.id]))
    php = zipfile.ZipFile(io.BytesIO(plugin.content)).read("bookpilot-connect/bookpilot-connect.php").decode()
    assert "Version: 1.3.0" in php and "bookpilot-add" in php and "/order.js" in php
    ac.post(reverse("webapp:kit_detail", args=[company.id]), {"action": "ordering"})
    assert RestaurantProfile.objects.get(company=company).web_orders_enabled is False


def test_auto_accept_sends_straight_to_kitchen():
    company, owner, kit = _restaurant("o7@t.qa")
    owner.post(reverse("webapp:restaurant_online_settings"), {**SETTINGS, "web_auto_accept": "on"})
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    r = _order(kit, items=[{"id": biryani.product_id, "qty": 1}])
    assert r.status_code == 201 and r.json()["accepted"] is True
    assert OnlineOrder.objects.for_company(company).get().order.status == "kitchen"
