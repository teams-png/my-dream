"""Own delivery riders: areas and charges, assign → on the way → delivered, the rider's private page,
cash with the rider, handing it over (which bills the orders) and the report."""
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.verticals.restaurant import delivery
from apps.verticals.restaurant.models import DeliveryHandover, DeliveryRider, DeliveryZone, RestaurantOrder

from .test_online_orders import _item, _restaurant

pytestmark = pytest.mark.django_db
ACT = "webapp:restaurant_delivery_action"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _setup(email):
    company, owner, _kit = _restaurant(email)
    owner.post(reverse(ACT), {"do": "rider_save", "name": "Ajmal", "phone": "+974 5555 7777", "vehicle": "Bike"})
    owner.post(reverse(ACT), {"do": "zone_save", "name": "Al Sadd", "fee": "10", "free_over": "0", "minutes": "30"})
    rider = DeliveryRider.objects.get(company=company)
    zone = DeliveryZone.objects.get(company=company)
    r = owner.post(reverse("webapp:restaurant_order_add"), {
        "channel": "delivery", "delivery_address": "Villa 12, Al Sadd St", "delivery_phone": "+974 5555 1234", "zone": zone.id})
    order = RestaurantOrder.objects.for_company(company).get(channel="delivery")
    assert r.status_code == 302 and order.delivery_status == "waiting" and order.zone == zone
    biryani = _item(company, "KL-thalassery-chicken-biryani")
    owner.post(reverse("webapp:restaurant_order_detail", args=[order.id]),
               {"action": "quick_add", "product_id": biryani.product_id, "quantity": 2})
    order.refresh_from_db()
    return company, owner, rider, order


def test_full_cash_delivery_and_handover():
    company, owner, rider, order = _setup("d1@t.qa")
    fee = sum(l.total for l in order.lines.all() if l.product.sku == delivery.FEE_SKU)
    assert fee == Decimal("10")
    board = owner.get(reverse("webapp:restaurant_deliveries")).content.decode()
    assert order.order_number in board and "Ajmal" in board and "Villa 12" in board

    owner.post(reverse(ACT), {"do": "assign", "order_id": order.id, "rider_id": rider.id})
    order.refresh_from_db()
    assert order.delivery_status == "assigned" and order.rider == rider

    # the rider's own page: no login, only their orders
    page = Client()
    url = reverse("webapp:delivery_rider_page", args=[rider.token])
    html = page.get(url).content.decode()
    assert order.order_number in html and "Villa 12" in html and "google.com/maps" in html and "Delivery charge" not in html
    assert "no-referrer" not in html  # it would send Origin: null and the buttons would fail the CSRF check
    page.post(url, {"order_id": order.id, "do": "out"})
    order.refresh_from_db()
    assert order.delivery_status == "out" and order.dispatched_at
    wa = delivery.customer_whatsapp(order)
    assert wa.startswith("https://wa.me/97455551234") and "Ajmal" in wa.replace("%20", " ")
    page.post(url, {"order_id": order.id, "do": "delivered", "method": "cash"})
    order.refresh_from_db()
    assert order.delivery_status == "delivered" and order.collect_method == "cash" and order.status != "paid"
    total = order.total
    assert delivery.cash_with(rider) == total

    owner.post(reverse(ACT), {"do": "handover", "rider_id": rider.id})
    order.refresh_from_db()
    record = DeliveryHandover.objects.get(company=company)
    assert order.status == "paid" and order.invoice and order.handover == record
    assert record.cash == total and record.orders_count == 1 and delivery.cash_with(rider) == 0

    report = owner.get(reverse("webapp:restaurant_delivery_report")).content.decode()
    assert "Ajmal" in report and f"{total:.2f}" in report


def test_card_failed_reassign_and_private_link():
    company, owner, rider, order = _setup("d2@t.qa")
    other = DeliveryRider.objects.create(company=company, name="Basil", phone="+974 5555 8888")
    owner.post(reverse(ACT), {"do": "assign", "order_id": order.id, "rider_id": rider.id})
    owner.post(reverse(ACT), {"do": "out", "order_id": order.id})
    # another rider's link cannot touch this order
    assert Client().post(reverse("webapp:delivery_rider_page", args=[other.token]),
                         {"order_id": order.id, "do": "delivered", "method": "cash"}).status_code == 404
    owner.post(reverse(ACT), {"do": "failed", "order_id": order.id, "reason": "Not answering"})
    order.refresh_from_db()
    assert order.delivery_status == "failed" and order.delivery_note == "Not answering"
    owner.post(reverse(ACT), {"do": "assign", "order_id": order.id, "rider_id": other.id})
    owner.post(reverse(ACT), {"do": "out", "order_id": order.id})
    owner.post(reverse(ACT), {"do": "delivered", "order_id": order.id, "method": "card"})
    owner.post(reverse(ACT), {"do": "handover", "rider_id": other.id})
    record = DeliveryHandover.objects.get(rider=other)
    order.refresh_from_db()
    assert record.card == order.total and record.cash == 0 and order.status == "paid"

    old = rider.token
    owner.post(reverse(ACT), {"do": "rider_new_link", "rider_id": rider.id})
    assert Client().get(reverse("webapp:delivery_rider_page", args=[old])).status_code == 404
    owner.post(reverse(ACT), {"do": "rider_toggle", "rider_id": rider.id})
    rider.refresh_from_db()
    assert not rider.is_active
    assert Client().get(reverse("webapp:delivery_rider_page", args=[rider.token])).status_code == 404


def test_free_over_paid_before_leaving_and_other_shops():
    company, owner, rider, order = _setup("d3@t.qa")
    zone = order.zone
    zone.free_over = Decimal("1")
    zone.save()
    owner.post(reverse(ACT), {"do": "zone", "order_id": order.id, "zone_id": zone.id})
    order.refresh_from_db()
    assert not [l for l in order.lines.all() if l.product.sku == delivery.FEE_SKU]  # free above the limit
    owner.post(reverse(ACT), {"do": "assign", "order_id": order.id, "rider_id": rider.id})
    order.refresh_from_db()
    delivery.dispatch(order)
    order.status = "paid"
    order.save(update_fields=["status"])
    delivery.deliver(order, "cash")
    assert order.collect_method == "prepaid" and delivery.cash_with(rider) == 0

    _c, other_owner, _o, _order = _setup("d4@t.qa")  # another restaurant cannot touch this order
    assert other_owner.post(reverse(ACT), {"do": "assign", "order_id": order.id, "rider_id": rider.id}).status_code == 404
