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
    _admin_save(admin_client, company, **{"a-package": "shop"})
    owner.post(reverse("webapp:site_editor"), _design_data(**{"d-custom_css": ".hero{color:red}</style><script>alert(1)</script>"}))
    owner.post(reverse("webapp:shop_order_settings"), {"s-shop_enabled": "on", "s-shop_pickup": "on", "s-shop_delivery": "on",
               "s-shop_delivery_fee": "15", "s-shop_free_delivery_over": "500", "s-shop_minimum": "0", "s-shop_note": "Cash on delivery",
               "s-shop_coupons": "on", "s-shop_online_payment": "on", "s-shop_reviews": "on"})
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

    _admin_save(admin_client, company, **{"a-custom_domain": "www.pcworld.qa", "a-domain_status": "live", "a-package": "shop"})
    cache.clear()
    domain = Client(HTTP_HOST="pcworld.qa")
    assert domain.get("/").status_code == 200
    shop_page = domain.get("/shop/").content.decode()
    assert 'href="/shop/' in shop_page
    assert domain.get("/p/warranty-returns/").status_code == 200
    assert "/shop/" in domain.get("/sitemap.xml").content.decode()
    assert domain.get("/login/").status_code == 404  # the client's domain never opens the BookPilot app


def test_shop_filters_side_bar(shop):
    from apps.inventory.models import Brand, Product, ProductCategory, Unit
    company, owner, kit = shop
    cat = ProductCategory.objects.create(company=company, name="Tees")
    unit = Unit.objects.filter(company=company).first()
    nike, puma = Brand.objects.create(company=company, name="Nike"), Brand.objects.create(company=company, name="Puma")
    for i, (brand, colour, size, price, ram) in enumerate([(nike, "Red", "M", 50, "8GB"), (nike, "Blue", "L", 80, "16GB"),
                                                           (puma, "Red", "S", 120, "16GB")]):
        Product.objects.create(company=company, sku=f"T{i}", name=f"Tee {i}", category=cat, brand=brand, colour=colour,
                               size=size, unit=unit, selling_price=price, is_stock_tracked=False, tracking_type="none",
                               attributes={"ram": ram})
    base = f"/site/{kit.public_id}/shop/"
    page = Client().get(base, {"cat": cat.id}).content.decode()
    assert 'name="brand"' in page and 'name="colour"' in page and 'name="size"' in page and 'name="a_ram"' in page
    assert "Nike" in page and "Puma" in page and ">S<" in page.replace("\n", "")

    def names(**params):
        html = Client().get(base, {"cat": cat.id, **params}).content.decode()
        return {n for n in ("Tee 0", "Tee 1", "Tee 2") if n in html}
    assert names(brand=str(nike.id)) == {"Tee 0", "Tee 1"}
    assert names(colour="Red") == {"Tee 0", "Tee 2"}
    assert names(colour="Red", brand=str(nike.id)) == {"Tee 0"}
    assert names(size=["S", "L"]) == {"Tee 1", "Tee 2"}
    assert names(min="60", max="100") == {"Tee 1"}
    assert names(a_ram="16GB") == {"Tee 1", "Tee 2"}
    chips = Client().get(base, {"cat": cat.id, "colour": "Red"}).content.decode()
    assert "Red ✕" in chips and "Clear all" in chips


def test_website_packages_billing_and_cart_only_for_ecommerce(shop, admin_client):
    from apps.industry import shop_orders
    from apps.subscriptions.pricing import addons
    company, owner, kit = shop
    sub = getattr(company, "subscription", None)
    if sub is not None:
        assert addons(sub)["website_amount"] == 699
    assert shop_orders.config(company) is not None
    _admin_save(admin_client, company, **{"a-package": "website"})
    cache.clear()
    assert shop_orders.config(company) is None
    home = Client().get(f"/site/{kit.public_id}/").content.decode()
    assert "data-bp-add" not in home and "/shop/" in home  # products still shown, no cart
    assert "E-commerce website package" in owner.get(reverse("webapp:shop_orders")).content.decode()
    if sub is not None:
        assert addons(sub)["website_amount"] == 399
    landing = Client().get(reverse("webapp:landing")).content.decode()
    assert "E-commerce website" in landing and '"shop": 699' in landing


def test_offers_coupon_reviews_gallery_wishlist_and_online_pay(shop, monkeypatch):
    import datetime
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.utils import timezone
    from apps.industry import shop_orders
    from apps.industry.models import ProductPhoto, ProductReview
    from apps.inventory.models import Product
    from apps.sales.models import Coupon, Promotion
    company, owner, kit = shop
    base = f"/site/{kit.public_id}/"
    item = Product.objects.filter(company=company, is_stock_tracked=True, variants__isnull=True).first()
    today = timezone.localdate()
    Promotion.objects.create(company=company, name="Big sale", product=item, discount_type="percentage",
                             discount_value=10, start_date=today, end_date=today + datetime.timedelta(days=5), is_active=True)
    cache.clear()
    offer = (item.selling_price * Decimal("0.9")).quantize(Decimal("0.01"))
    page = Client().get(f"{base}shop/{item.id}/").content.decode()
    assert f"{offer:.2f}" in page and "Big sale" in page and '"@type":"Product"' in page and "Write a review" in page

    Coupon.objects.create(company=company, code="EID10", discount_type="fixed", discount_value=20,
                          start_date=today, expiry_date=today + datetime.timedelta(days=5))
    ok = Client().get(reverse("webapp:kit_coupon", args=[kit.public_id]), {"code": "eid10", "subtotal": "500"}).json()
    assert ok["ok"] and ok["discount"] == "20.00"
    assert not Client().get(reverse("webapp:kit_coupon", args=[kit.public_id]), {"code": "NOPE", "subtotal": "500"}).json()["ok"]

    r = Client().post(reverse("webapp:kit_order", args=[kit.public_id]), json.dumps({
        "name": "Huda", "phone": "+974 5555 8888", "mode": "pickup", "coupon": "EID10",
        "items": [{"id": item.id, "qty": 1}]}), content_type="application/json", REMOTE_ADDR="10.30.0.1")
    assert r.status_code == 201, r.content
    order = ShopOrder.objects.get(number=r.json()["reference"])
    assert order.lines.get().unit_price == offer and order.discount == 20 and order.total == offer - 20
    assert "pay_url" not in r.json()

    monkeypatch.setattr(shop_orders, "online_ready", lambda company: True)
    r = Client().post(reverse("webapp:kit_order", args=[kit.public_id]), json.dumps({
        "name": "Huda", "phone": "+974 5555 8888", "mode": "pickup", "payment": "online",
        "items": [{"id": item.id, "qty": 1}]}), content_type="application/json", REMOTE_ADDR="10.30.0.2")
    paid = ShopOrder.objects.get(number=r.json()["reference"])
    assert paid.payment_method == "online" and paid.invoice and r.json()["pay_url"].startswith("http")
    assert paid.status == "new"
    owner.post(reverse("webapp:shop_order_action", args=[paid.id]), {"do": "bill"})
    paid.refresh_from_db()
    assert paid.status == "done" and ShopOrder.objects.filter(invoice=paid.invoice).count() == 1

    # reviews wait for approval
    Client().post(f"{base}shop/{item.id}/review/", {"name": "Ali", "rating": "4", "text": "Fast laptop"})
    rv = ProductReview.objects.get(company=company)
    assert not rv.is_approved and "Fast laptop" in owner.get(reverse("webapp:shop_orders")).content.decode()
    owner.post(reverse("webapp:shop_review_action", args=[rv.id]), {"do": "approve"})
    cache.clear()
    assert "Fast laptop" in Client().get(f"{base}shop/{item.id}/").content.decode()

    # gallery
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, "PNG")
    pic = SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png")
    form = owner.get(reverse("webapp:product_edit", args=[item.id])).content.decode()
    assert 'name="gallery"' in form and "multiple" in form
    from apps.webapp.forms import BusinessProductForm, save_product_gallery
    f = BusinessProductForm(data={"sku": item.sku, "name": item.name, "unit": item.unit_id, "cost_price": "1",
                                  "selling_price": str(item.selling_price), "reorder_level": "0"},
                            files={"gallery": [pic]}, instance=item, company=company)
    f.is_valid()
    save_product_gallery(f, item)
    assert ProductPhoto.objects.filter(product=item).count() == 1
    cache.clear()
    assert 'class="thumbs"' in Client().get(f"{base}shop/{item.id}/").content.decode()

    # wishlist view
    wl = Client().get(f"{base}shop/", {"ids": str(item.id)}).content.decode()
    assert "My wishlist" in wl and "1 product" in wl


def test_shop_widget_for_wordpress_and_bootstrap_sites(shop, admin_client):
    import io
    import zipfile
    from apps.inventory.models import Product
    company, owner, kit = shop
    item = Product.objects.filter(company=company, is_stock_tracked=True, variants__isnull=True).first()
    js = Client().get(reverse("webapp:kit_shop_js", args=[kit.public_id])).content.decode()
    assert "bookpilot-shop" in js and "/shop.json" in js and "/order.js" in js
    data = Client().get(reverse("webapp:kit_shop_json", args=[kit.public_id]), {"q": item.name[:5]}).json()
    assert data["total"] >= 1 and any(i["id"] == item.id for i in data["items"]) and "brand" in data["facets"]
    assert Client().get(reverse("webapp:kit_shop_json", args=[kit.public_id])).get("Access-Control-Allow-Origin") == "*"
    prod = Client().get(reverse("webapp:kit_product_json", args=[kit.public_id, item.id])).json()
    assert prod["item"]["name"] == item.name and prod["ordering"] is True
    r = Client().post(reverse("webapp:kit_review", args=[kit.public_id, item.id]), json.dumps({"name": "Sam", "rating": 5}),
                      content_type="application/json", HTTP_ORIGIN="https://shop.example")
    assert r.status_code == 201
    from apps.industry.models import ProductReview
    assert ProductReview.objects.filter(product=item, name="Sam", is_approved=False).exists()

    plugin = zipfile.ZipFile(io.BytesIO(admin_client.get(reverse("webapp:kit_wp_plugin", args=[company.id])).content))
    php = plugin.read("bookpilot-connect/bookpilot-connect.php").decode()
    assert "add_shortcode('bookpilot_shop'" in php
    starter = zipfile.ZipFile(io.BytesIO(admin_client.get(reverse("webapp:kit_bootstrap_starter", args=[company.id])).content))
    names = starter.namelist()
    assert any(n.endswith("shop.html") for n in names) and any(n.endswith("assets/style.css") for n in names)
    shop_html = starter.read([n for n in names if n.endswith("shop.html")][0]).decode()
    assert 'class="bookpilot-shop"' in shop_html and "bootstrap@5" in shop_html and "/shop.js" in shop_html
    page = admin_client.get(reverse("webapp:kit_detail", args=[company.id])).content.decode()
    assert "Full online shop" in page and "Bootstrap website starter" in page


def test_custom_bootstrap_design_with_placeholders(shop, admin_client):
    from apps.webapp.site_views import BOOTSTRAP_STARTER
    company, owner, kit = shop
    editor = admin_client.get(reverse("webapp:site_admin_editor", args=[company.id])).content.decode()
    assert "Load Bootstrap 5 starter" in editor and "[[menu_items]]" in editor
    _admin_save(admin_client, company, **{"a-package": "shop", **{f"a-{k}": v for k, v in BOOTSTRAP_STARTER.items()}})
    cache.clear()
    base = f"/site/{kit.public_id}/"
    home = Client().get(base).content.decode()
    assert "bootstrap@5.3.3" in home and 'class="navbar navbar-expand-lg' in home and "[[" not in home
    assert f'href="{base}shop/"' in home and 'class="nav-item"' in home and "data-bp-add" in home
    assert 'class="bookpilot-enquiry"' in home and "Popular products" in home and 'class="chips"' in home
    shop_page = Client().get(base + "shop/").content.decode()
    assert 'class="navbar navbar-expand-lg' in shop_page and 'id="filterForm"' in shop_page and "bg-dark text-light" in shop_page
