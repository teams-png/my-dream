"""Retail POS checkout service, idempotent live checkout and offline sync."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.inventory.services import record_stock_movement
from apps.sales import pos
from apps.sales.models import OfflineSaleSync, SalesInvoice

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    record_stock_movement(company=tenant_a, product=data["product"], warehouse=data["warehouse"],
                          quantity=Decimal("5"), reason="adjustment", reference="opening")
    return {**data, "company": tenant_a, "user": tenant_a_owner}


def _sale(shop, qty=1, **extra):
    return {"client_id": str(uuid.uuid4()), "offline_number": "OFF-T-0001", "payment_method": "cash",
            "created_at": timezone.now().isoformat(), "total": "100.00",
            "lines": [{"product_id": shop["product"].id, "quantity": qty, "unit_price": "100.00", "name": "Thing"}],
            **extra}


def test_checkout_books_invoice_and_payment(shop):
    result = pos.checkout(company=shop["company"], user=shop["user"], payload=_sale(shop, qty=2))
    invoice = SalesInvoice.objects.get(id=result["invoice_id"])
    assert invoice.total == Decimal("200")
    assert result["balance"] == "0.00"
    assert shop["product"].current_stock() == Decimal("3")


def test_checkout_rolls_back_everything_on_error(shop):
    # a walk-in credit sale must fail *before* anything is stored
    with pytest.raises(pos.PosError):
        pos.checkout(company=shop["company"], user=shop["user"], payload=_sale(shop, payment_method="credit"))
    assert not SalesInvoice.objects.filter(company=shop["company"]).exists()
    assert shop["product"].current_stock() == Decimal("5")


def test_checkout_rejects_other_companies_products(shop, tenant_b, sales_fixtures_factory):
    other = sales_fixtures_factory(tenant_b, sku="B-1")
    payload = _sale(shop)
    payload["lines"][0]["product_id"] = other["product"].id
    with pytest.raises(pos.PosError):
        pos.checkout(company=shop["company"], user=shop["user"], payload=payload)


def test_live_checkout_with_same_client_id_bills_once(shop):
    payload = _sale(shop)
    first = pos.live_checkout(company=shop["company"], user=shop["user"], payload=payload)
    again = pos.live_checkout(company=shop["company"], user=shop["user"], payload=payload)
    assert first["invoice_id"] == again["invoice_id"]
    assert SalesInvoice.objects.filter(company=shop["company"]).count() == 1


def test_offline_sync_is_idempotent_and_uses_sale_day(shop):
    payload = _sale(shop, created_at=(timezone.now() - timedelta(days=2)).isoformat())
    record = pos.sync_offline_sale(company=shop["company"], user=shop["user"], payload=payload)
    again = pos.sync_offline_sale(company=shop["company"], user=shop["user"], payload=payload)
    assert record.status == again.status == "synced"
    assert record.invoice_id == again.invoice_id
    assert SalesInvoice.objects.filter(company=shop["company"]).count() == 1
    assert record.invoice.date == timezone.localdate() - timedelta(days=2)


def test_sale_that_timed_out_live_is_not_billed_again_by_sync(shop):
    payload = _sale(shop)
    pos.live_checkout(company=shop["company"], user=shop["user"], payload=payload)  # answer never reached the till
    record = pos.sync_offline_sale(company=shop["company"], user=shop["user"], payload=payload)
    assert record.status == "synced"
    assert SalesInvoice.objects.filter(company=shop["company"]).count() == 1


def test_offline_sale_that_cannot_be_booked_needs_attention_then_retries(shop):
    payload = _sale(shop)
    payload["lines"][0]["product_id"] = 999999
    record = pos.sync_offline_sale(company=shop["company"], user=shop["user"], payload=payload)
    assert record.status == "attention" and record.invoice is None and record.error
    record.payload["lines"][0]["product_id"] = shop["product"].id
    record.save()
    record = pos.retry(record, user=shop["user"])
    assert record.status == "synced" and record.invoice is not None


def test_offline_sync_never_uses_credit_or_coupons(shop):
    record = pos.sync_offline_sale(company=shop["company"], user=shop["user"],
                                   payload=_sale(shop, payment_method="credit", coupon_code="FREE"))
    assert record.status == "synced"
    assert record.invoice.amount_paid == record.invoice.total


def test_future_device_clock_books_today(shop):
    record = pos.sync_offline_sale(company=shop["company"], user=shop["user"],
                                   payload=_sale(shop, created_at=(timezone.now() + timedelta(days=40)).isoformat()))
    assert record.invoice.date == timezone.localdate()


def test_views_checkout_sync_and_attention_list(client, shop):
    client.force_login(shop["user"])
    page = client.get(reverse("webapp:pos"))
    assert page.status_code == 200
    assert b"posData" in page.content and b"retail-pos.js" in page.content

    resp = client.post(reverse("webapp:pos_checkout"), json.dumps(_sale(shop)), content_type="application/json")
    assert resp.status_code == 200 and resp.json()["invoice_number"]

    good, bad = _sale(shop), _sale(shop)
    bad["lines"][0]["product_id"] = 424242
    resp = client.post(reverse("webapp:pos_offline_sync"), json.dumps({"sales": [good, bad, "junk"]}),
                       content_type="application/json")
    statuses = [r["status"] for r in resp.json()["results"]]
    assert statuses == ["synced", "attention", "error"]

    listing = client.get(reverse("webapp:pos_offline_sales"))
    assert listing.status_code == 200
    assert listing.context["counts"] == {"attention": 1, "synced": 1, "resolved": 0}  # live sale not listed

    record = OfflineSaleSync.objects.get(client_id=bad["client_id"])
    client.post(reverse("webapp:pos_offline_sales"), {"record_id": record.id, "action": "resolve"})
    record.refresh_from_db()
    assert record.status == "resolved"


def test_sync_endpoint_is_company_scoped(client, shop, tenant_b, tenant_b_owner):
    payload = _sale(shop)
    client.force_login(tenant_b_owner)
    resp = client.post(reverse("webapp:pos_offline_sync"), json.dumps({"sales": [payload]}), content_type="application/json")
    if resp.status_code == 200:
        assert resp.json()["results"][0]["status"] == "attention"  # B cannot sell A's product
    assert not SalesInvoice.objects.filter(company__in=[shop["company"], tenant_b]).exists()
