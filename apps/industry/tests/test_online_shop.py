"""A shop's website is a real online shop: home, Shop page, a page per product, the owner's own pages and CSS,
a cart that sends orders to BookPilot, and the client's own domain (e.g. bought at Hostinger)."""
import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.industry import website_kit
from apps.industry.models import ShopOrder, SiteDesign, SitePage
from apps.industry.tests.test_site_builder import _admin_save, _design_data, _signup, admin_client  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(admin_client):
    from apps.industry import sample_kit
    from apps.accounts.models import User
    with override_settings(SAMPLE_DATA_KIT=False):
        company, owner = _signup("computer_shop", "pc@shop.qa")
    with override_settings(SAMPLE_DATA_KIT=True):
        sample_kit.install(company, User.objects.get(email="pc@shop.qa"))
    _admin_save(admin_client, company)
    owner.post(reverse("webapp:site_editor"), _design_data(**{"d-custom_css": ".hero{color:red}</style><script>alert(1)</script>"}))
    owner.post(reverse("webapp:shop_order_settings"), {"s-shop_enabled": "on", "s-shop_pickup": "on", "s-shop_delivery": "on",
               "s-shop_delivery_fee": "15", "s-shop_free_delivery_over": "500", "s-shop_minimum": "0", "s-shop_note": "Cash on delivery"})
    kit = website_kit.kit_for(company)
    return company, owner, kit


def test_shop_pages_cart_order_inbox_and_bill(shop):
    from apps.inventory.models import Product
    company, owner, kit = shop
    design = SiteDesign.objects.get(company=company)
    assert design.shop_enabled
    visitor = Client()
    base = f"/site/{kit.public_id}/"

    home = visitor.get(base).content.decode()
    assert f'href="{base}shop/"' in home and "Popular products" in home and "data-bp-add" in home
    assert "<script>alert(1)</script>" not in home and ".hero{color:red}" in home  # owner CSS kept, script dropped

    laptop = Product.objects.filter(company=company, is_stock_tracked=True, variants__isnull=True).first()
    page = visitor.get(base + "shop/").content.decode()
    assert escape(laptop.name) in page and f"{base}shop/{laptop.id}/" in page
    found = visitor.get(base + "shop/", {"q": laptop.name[:5]}).content.decode()
    assert escape(laptop.name) in found
    if laptop.category_id:
        assert escape(laptop.name) in visitor.get(base + "shop/", {"cat": laptop.category_id}).content.decode()

    detail = visitor.get(f"{base}shop/{laptop.id}/").content.decode()
    assert "Add to cart" in detail and ("In stock" in detail or "left" in detail) and 'og:type" content="product"' in detail
    assert visitor.get(f"{base}shop/999999/").status_code == 404

    js = visitor.get(reverse("webapp:kit_order_js", args=[kit.public_id])).content.decode()
    assert '"shop": true' in js and "The shop will confirm" in js

    stock_before = laptop.current_stock()
    r = visitor.post(reverse("webapp:kit_order", args=[kit.public_id]), json.dumps({
        "name": "Rashid", "phone": "+974 5555 7777", "email": "r@x.qa", "mode": "delivery", "address": "Zone 24, Street 5, Villa 9",
        "items": [{"id": laptop.id, "qty": 1}]}), content_type="application/json", REMOTE_ADDR="10.20.0.1")
    assert r.status_code == 201, r.content
    data = r.json()
    order = ShopOrder.objects.get(company=company, number=data["reference"])
    expected_fee = Decimal("0") if laptop.selling_price >= 500 else Decimal("15")
    assert order.delivery_fee == expected_fee and order.total == laptop.selling_price + expected_fee
    assert order.lines.get().product == laptop and laptop.current_stock() == stock_before  # stock moves when billed

    too_many = visitor.post(reverse("webapp:kit_order", args=[kit.public_id]), json.dumps({
        "name": "Rashid", "phone": "+974 5555 7777", "mode": "pickup", "items": [{"id": laptop.id, "qty": int(stock_before) + 1}]}),
        content_type="application/json", REMOTE_ADDR="10.20.0.2")
    assert too_many.status_code == 400 and "left" in too_many.json()["error"]

    status = visitor.get(data["track_url"]).content.decode()
    assert order.number in status and "will confirm" in status

    inbox = owner.get(reverse("webapp:shop_orders")).content.decode()
    assert order.number in inbox and "Rashid" in inbox and "wa.me/974" in inbox
    assert owner.get(reverse("webapp:shop_orders_waiting")).json()["count"] == 1
    owner.post(reverse("webapp:shop_order_action", args=[order.id]), {"do": "confirm"})
    owner.post(reverse("webapp:shop_order_action", args=[order.id]), {"do": "ready"})
    owner.post(reverse("webapp:shop_order_action", args=[order.id]), {"do": "bill"})
    order.refresh_from_db()
    assert order.status == "done" and order.invoice and order.invoice.total == order.total
    assert laptop.current_stock() == stock_before - 1
    assert "on its way" in visitor.get(data["track_url"]).content.decode() or "Thank you" in visitor.get(data["track_url"]).content.decode()


def test_owner_pages_and_own_domain(shop, admin_client):
    company, owner, kit = shop
    r = owner.post(reverse("webapp:site_editor"), {"action": "page_save", "pg-title": "Warranty & returns", "pg-slug": "",
                   "pg-body": "<h2>1 year warranty</h2><p onclick='x()'>Bring the bill.</p><script>steal()</script>"
                              "<iframe src='https://evil.example/'></iframe><a href='javascript:alert(1)'>x</a>",
                   "pg-show_in_menu": "on", "pg-published": "on"})
    assert r.status_code == 302
    page = SitePage.objects.get(company=company)
    assert page.slug == "warranty-returns"
    html = Client().get(f"/site/{kit.public_id}/p/warranty-returns/").content.decode()
    body = html.split('<div class="rich">', 1)[1].split("</div></section>", 1)[0]
    assert "steal()" not in html
    assert "1 year warranty" in body and "Bring the bill." in body
    assert "steal()" not in body and "onclick" not in body and "evil.example" not in body and "javascript:" not in body
    home = Client().get(f"/site/{kit.public_id}/").content.decode()
    assert "Warranty &amp; returns" in home  # in the top menu

    _admin_save(admin_client, company, **{"a-custom_domain": "www.pcworld.qa", "a-domain_status": "live"})
    cache.clear()
    domain = Client(HTTP_HOST="pcworld.qa")
    assert domain.get("/").status_code == 200
    shop_page = domain.get("/shop/").content.decode()
    assert 'href="/shop/' in shop_page
    assert domain.get("/p/warranty-returns/").status_code == 200
    assert "/shop/" in domain.get("/sitemap.xml").content.decode()
    assert domain.get("/login/").status_code == 404  # the client's domain never opens the BookPilot app
