from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.inventory.models import ProductBatch, ProductSerial, StockCount, Warehouse
from apps.inventory.services import record_stock_movement
from apps.sales import services as sales

pytestmark = pytest.mark.django_db


@pytest.fixture
def store(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="MILK", stock_price=Decimal("10"))
    record_stock_movement(company=tenant_a, product=base["product"], warehouse=base["warehouse"], quantity=40, reason="purchase")
    branch = Warehouse.objects.create(company=tenant_a, name="Branch 2")
    client.force_login(tenant_a_owner)
    return {"client": client, "company": tenant_a, "user": tenant_a_owner, "branch": branch, **base}


def test_overview_adjust_and_transfer(store):
    client, product, main, branch = store["client"], store["product"], store["warehouse"], store["branch"]
    page = client.get(reverse("webapp:stock_home"))
    assert page.status_code == 200 and page.context["stats"]["value"] == Decimal("200")
    client.post(reverse("webapp:stock_adjust"), {"product": product.id, "warehouse": main.id, "direction": "out",
                                                 "quantity": "3", "reason": "damaged", "note": "broken"})
    assert product.current_stock(main) == Decimal("37")
    client.post(reverse("webapp:stock_transfer"), {"from": main.id, "to": branch.id, "reference": "Van",
                                                   "product": [product.id, ""], "qty": ["10", ""]})
    assert product.current_stock(main) == Decimal("27") and product.current_stock(branch) == Decimal("10")
    client.post(reverse("webapp:stock_transfer"), {"from": main.id, "to": branch.id, "product": [product.id], "qty": ["500"]})
    assert product.current_stock(branch) == Decimal("10")  # not enough stock: refused
    history = client.get(reverse("webapp:stock_history", args=[product.id]))
    assert history.context["balance"] == Decimal("37")
    assert client.get(reverse("webapp:stock_transfer")).status_code == 200


def test_stock_count_corrects_only_counted_items(store):
    client, product, main = store["client"], store["product"], store["warehouse"]
    client.post(reverse("webapp:count_list"), {"warehouse": main.id})
    count = StockCount.objects.get(company=store["company"])
    line = count.lines.get()
    client.post(reverse("webapp:count_detail", args=[count.id]), {f"c_{line.id}": "36", "action": "save"})
    line.refresh_from_db()
    assert line.counted_quantity == Decimal("36") and product.current_stock(main) == Decimal("40")
    page = client.get(reverse("webapp:count_detail", args=[count.id]))
    assert page.context["short_value"] == Decimal("20")
    client.post(reverse("webapp:count_detail", args=[count.id]), {f"c_{line.id}": "36", "action": "complete"})
    count.refresh_from_db()
    assert count.status == "completed" and product.current_stock(main) == Decimal("36")


def test_batches_expiry_and_fefo_sale(store):
    client, product, main = store["client"], store["product"], store["warehouse"]
    today = date.today()
    client.post(reverse("webapp:stock_batches"), {"product": product.id, "batch_number": "B-LATE", "expiry_date": (today + timedelta(days=90)).isoformat(),
                                                  "quantity": "5", "warehouse": main.id})
    client.post(reverse("webapp:stock_batches"), {"product": product.id, "batch_number": "B-SOON", "expiry_date": (today + timedelta(days=10)).isoformat(),
                                                  "quantity": "4", "warehouse": main.id})
    soon = ProductBatch.objects.get(batch_number="B-SOON")
    late = ProductBatch.objects.get(batch_number="B-LATE")
    page = client.get(reverse("webapp:stock_batches"), {"show": "expiring"})
    assert [r["b"].batch_number for r in page.context["rows"]] == ["B-SOON"]
    # a sale without a chosen batch takes the earliest-expiring batch first
    product.refresh_from_db()
    sales.create_invoice(company=store["company"], user=store["user"], customer=store["customer"], date=today, warehouse=main,
                         lines=[{"product": product, "quantity": Decimal("6"), "unit_price": Decimal("10")}])
    from apps.inventory.services import available_batch_quantity
    assert available_batch_quantity(company=store["company"], product=product, warehouse=main, batch=soon) == 0
    assert available_batch_quantity(company=store["company"], product=product, warehouse=main, batch=late) == Decimal("3")


def test_serials_register_and_lookup(store):
    client, product, main = store["client"], store["product"], store["warehouse"]
    client.post(reverse("webapp:stock_serials"), {"product": product.id, "warehouse": main.id, "serials": "IMEI1\nIMEI2\nIMEI1"})
    assert ProductSerial.objects.filter(product=product).count() == 2
    client.post(reverse("webapp:stock_serials"), {"product": product.id, "warehouse": main.id, "serials": "IMEI2"})
    assert ProductSerial.objects.filter(product=product).count() == 2
    page = client.get(reverse("webapp:stock_serials"), {"q": "imei1"})
    assert page.context["found"].serial_number == "IMEI1"
