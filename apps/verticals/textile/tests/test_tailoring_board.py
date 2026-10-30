"""Tailoring orders: garment and advance on the order, a cut / stitching / ready board, WhatsApp and balance at delivery."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.tenants.models import Company
from apps.verticals.textile import services
from apps.verticals.textile.models import TailoringOrder

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Stitch Point", "business_type": "textile", "country": "India", "full_name": "Rema K",
        "email": "r@stitch.test", "phone": "", "password": "Stitch-Point-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email="r@stitch.test")


def test_order_with_advance_moves_across_the_board_and_collects_the_balance(client, shop):
    today = timezone.localdate()
    resp = client.post(reverse("webapp:order_add"), {
        "new_name": "Anitha", "new_phone": "+91 94470 11223", "garment": "Churidar set", "quantity": "2",
        "order_date": today.isoformat(), "expected_delivery_date": (today + timedelta(days=5)).isoformat(),
        "price": "1200", "advance": "500", "advance_method": "bank"})
    assert resp.status_code == 302
    order = TailoringOrder.objects.get(company=shop)
    assert order.customer.name == "Anitha" and order.garment == "Churidar set" and order.quantity == 2
    assert order.advance == Decimal("500") and services.balance(order) == Decimal("700")
    board = client.get(reverse("webapp:order_list")).content.decode()
    assert "Churidar set" in board and "Start stitching" in board
    assert client.get(reverse("webapp:order_mark_ready", args=[order.id])).status_code == 405
    client.post(reverse("webapp:order_start", args=[order.id]))
    client.post(reverse("webapp:order_mark_ready", args=[order.id]))
    order.refresh_from_db()
    assert order.status == "ready"
    assert "wa.me/919447011223" in client.get(reverse("webapp:order_list")).content.decode()
    assert "Balance: 700.00" in services.ready_message(order)
    client.post(reverse("webapp:order_mark_delivered", args=[order.id]), {"collect": "900", "method": "cash"})
    order.refresh_from_db()
    assert order.status == "delivered" and services.balance(order) == Decimal("0")
    assert order.sales_invoice.amount_paid == Decimal("1200")


def test_advance_cannot_exceed_the_charge(client, shop):
    Customer.objects.create(company=shop, name="Biju")
    today = timezone.localdate().isoformat()
    resp = client.post(reverse("webapp:order_add"), {
        "new_name": "Biju", "order_date": today, "expected_delivery_date": today, "price": "300", "advance": "400",
        "quantity": "1", "advance_method": "cash"})
    assert resp.status_code == 200 and not TailoringOrder.objects.filter(company=shop).exists()
