import uuid
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.inventory.models import Product
from apps.modules.models import BusinessType
from apps.verticals.restaurant import offline
from apps.verticals.restaurant.models import (
    DiningArea, DiningTable, OfflineOrderSync, RestaurantMenuItem, RestaurantOrder, RestaurantProfile,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner, sales_fixtures_factory):
    call_command("seed_platform")
    tenant_a.business_type = BusinessType.objects.get(code="restaurant")
    tenant_a.save(update_fields=["business_type"])
    base = sales_fixtures_factory(tenant_a, sku="ING")
    burger = Product.objects.create(company=tenant_a, sku="BURGER", name="Burger", unit=base["unit"],
                                    selling_price=20, is_stock_tracked=False, tracking_type="none")
    RestaurantMenuItem.objects.create(company=tenant_a, product=burger)
    table = DiningTable.objects.create(company=tenant_a, area=DiningArea.objects.create(company=tenant_a, name="Hall"), name="T1")
    RestaurantProfile.objects.update_or_create(company=tenant_a, defaults={"tax_percent": Decimal("5")})
    return {**base, "burger": burger, "table": table, "user": tenant_a_owner}


def bill(shop, **over):
    data = {"client_id": str(uuid.uuid4()), "offline_number": "OFF-AB-0001", "created_at": "2026-09-29T10:00:00+03:00",
            "channel": "takeaway", "tax_percent": "5.00",
            "lines": [{"id": "l1", "product_id": shop["burger"].id, "quantity": "2", "unit_price": "20.00", "modifier_ids": []}],
            "sent_line_ids": ["l1"], "paid": True, "paid_at": "2026-09-29T10:05:00+03:00",
            "payments": [{"method": "cash", "amount": "42.00"}]}
    data.update(over)
    return data


def test_paid_offline_bill_becomes_paid_order_once(tenant_a, shop):
    payload = bill(shop)
    rec = offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=payload)
    assert rec.status == "synced" and rec.order.status == "paid" and rec.order.invoice.transaction_total == Decimal("42.00")
    again = offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=payload)
    assert again.pk == rec.pk and RestaurantOrder.objects.filter(company=tenant_a).count() == 1


def test_open_dine_in_bill_syncs_then_gets_more_items_and_payment(tenant_a, shop):
    payload = bill(shop, channel="dine_in", table_id=shop["table"].id, guests=3, paid=False, payments=[])
    rec = offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=payload)
    order = rec.order
    assert order.status == "kitchen" and order.table == shop["table"] and order.guests == 3 and order.lines.count() == 1
    payload["lines"].append({"id": "l2", "product_id": shop["burger"].id, "quantity": "1", "unit_price": "20.00"})
    payload.update(paid=True, payments=[{"method": "card", "amount": "63.00"}])
    offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=payload)
    order.refresh_from_db()
    assert order.lines.count() == 2 and order.status == "paid"


def test_sale_keeps_offline_price_and_ignores_sold_out(tenant_a, shop):
    RestaurantMenuItem.objects.filter(product=shop["burger"]).update(is_available=False)
    shop["burger"].selling_price = 25
    shop["burger"].save(update_fields=["selling_price"])
    rec = offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=bill(shop))
    assert rec.status == "synced" and rec.order.lines.get().unit_price == Decimal("20.00")


def test_payment_mismatch_needs_attention_but_keeps_the_sale(tenant_a, shop):
    rec = offline.sync_offline_order(company=tenant_a, user=shop["user"], payload=bill(shop, payments=[{"method": "cash", "amount": "40"}]))
    assert rec.status == "attention" and "total" in rec.error.lower()
    assert rec.order.lines.count() == 1 and rec.order.status != "paid"


def test_sync_api_bootstrap_and_isolation(client, tenant_a, tenant_b, shop):
    from apps.tenants.models import CompanyMembership
    client.force_login(shop["user"])
    boot = client.get(reverse("webapp:restaurant_offline_bootstrap")).json()
    assert boot["items"][0]["name"] == "Burger" and boot["tax_percent"] == "5.00" and boot["csrf"]
    payload = bill(shop)
    resp = client.post(reverse("webapp:restaurant_offline_sync"), {"bills": [payload]}, content_type="application/json")
    assert resp.status_code == 200 and resp.json()["results"][0]["status"] == "synced"
    assert client.get(reverse("webapp:restaurant_offline_pos")).status_code == 200
    outsider = CompanyMembership.objects.filter(company=tenant_b).first().user
    client.force_login(outsider)
    resp = client.post(reverse("webapp:restaurant_offline_sync"), {"bills": [payload]}, content_type="application/json")
    assert OfflineOrderSync.objects.filter(company=tenant_b).count() == 0
