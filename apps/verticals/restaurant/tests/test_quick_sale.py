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


def test_card_approval_code_is_kept(counter):
    company, client = counter
    from apps.verticals.restaurant.models import RestaurantPaymentSplit
    chaya = Product.objects.for_company(company).get(sku="KL-chaya")
    data = client.post(reverse("webapp:restaurant_quick_sale_submit"),
                       json.dumps({"method": "card", "reference": "AP123456",
                                   "lines": [{"product": chaya.id, "qty": 2, "price": "1.50"}]}),
                       content_type="application/json").json()
    split = RestaurantPaymentSplit.objects.get(order__order_number=data["number"])
    assert (split.method, split.reference, split.amount) == ("card", "AP123456", Decimal("3.00"))


def test_offline_quick_bill_syncs_once_with_an_extra_item(counter):
    import uuid
    company, client = counter
    porotta = Product.objects.for_company(company).get(sku="KL-kerala-porotta")
    bill = {"client_id": str(uuid.uuid4()), "offline_number": "QABC-123456", "created_at": "2026-10-04T08:15:00Z",
            "paid_at": "2026-10-04T08:15:00Z", "channel": "takeaway", "tax_percent": "0.00", "paid": True, "pay_in_full": True,
            "payments": [{"method": "card", "amount": "6.99", "reference": "AP9"}],  # device total may differ by rounding
            "lines": [{"id": str(uuid.uuid4()), "product_id": porotta.id, "name": "Kerala Porotta", "quantity": 2, "unit_price": "1.50"},
                      {"id": str(uuid.uuid4()), "product_id": None, "name": "Plum cake", "quantity": 1, "unit_price": "4.00"}]}
    url = reverse("webapp:restaurant_offline_sync")
    first = client.post(url, json.dumps({"bills": [bill]}), content_type="application/json").json()["results"][0]
    again = client.post(url, json.dumps({"bills": [bill]}), content_type="application/json").json()["results"][0]
    assert first["status"] == "synced" and first["order_status"] == "paid" and again["order_id"] == first["order_id"]
    order = RestaurantOrder.objects.for_company(company).get(id=first["order_id"])
    assert order.invoice.total == Decimal("7.00") and order.invoice.amount_paid == Decimal("7.00")
    assert order.lines.count() == 2 and order.payment_splits.get().reference == "Offline QABC-123456 · AP9"
    assert Product.objects.for_company(company).filter(name="Plum cake", sku__startswith="QUICK-").exists()


def test_quick_page_is_cached_for_offline_use(counter):
    _company, client = counter
    sw = client.get("/service-worker.js").content.decode()
    assert "QUICK='/restaurant/quick/'" in sw
    page = client.get(reverse("webapp:restaurant_quick_sale")).content.decode()
    assert "qsCard" in page and "bp.quick.queue." in page and "/restaurant/offline/sync/" in page
