"""Product list: a price changed right in its cell, and many ticked products changed at once."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.inventory.models import Product, ProductCategory, Unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    a = Product.objects.create(company=tenant_a, sku="A1", name="Cable", unit=unit, selling_price=Decimal("10.00"))
    b = Product.objects.create(company=tenant_a, sku="B1", name="Charger", unit=unit, selling_price=Decimal("25.00"))
    return {"client": c, "a": a, "b": b, "company": tenant_a}


def test_inline_price_edit(shop, tenant_b):
    c, a = shop["client"], shop["a"]
    page = c.get(reverse("webapp:product_list")).content.decode()
    assert reverse("webapp:product_quick_update", args=[a.id]) in page and "data-bulk-form" in page
    url = reverse("webapp:product_quick_update", args=[a.id])
    r = c.post(url, {"field": "selling_price", "value": "12.5"})
    assert r.json() == {"ok": True, "value": "12.50"}
    a.refresh_from_db()
    assert a.selling_price == Decimal("12.50")
    assert c.post(url, {"field": "selling_price", "value": "-3"}).status_code == 400
    assert c.post(url, {"field": "name", "value": "x"}).status_code == 400
    other = Product.objects.create(company=tenant_b, sku="Z", name="Other", unit=Unit.objects.create(company=tenant_b, name="pcs"))
    assert c.post(reverse("webapp:product_quick_update", args=[other.id]), {"field": "selling_price", "value": "1"}).status_code == 404


def test_bulk_actions(shop):
    c, a, b = shop["client"], shop["a"], shop["b"]
    url = reverse("webapp:product_bulk")
    c.post(url, {"ids": [a.id, b.id], "action": "price_pct", "pct": "10"})
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.selling_price, b.selling_price) == (Decimal("11.00"), Decimal("27.50"))
    cat = ProductCategory.objects.create(company=shop["company"], name="Accessories")
    c.post(url, {"ids": [a.id], "action": "category", "category": cat.id})
    a.refresh_from_db()
    assert a.category == cat
    c.post(url, {"ids": [b.id], "action": "deactivate"})
    b.refresh_from_db()
    assert not b.is_active
    r = c.post(url, {"ids": [a.id], "action": "price_pct", "pct": "-95"}, follow=True)
    assert "between -90 and 500" in r.content.decode()
