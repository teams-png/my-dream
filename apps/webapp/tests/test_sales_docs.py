from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.customers.models import Customer
from apps.inventory.services import record_stock_movement
from apps.sales.models import DeliveryNote, Quotation, SalesInvoice, SalesOrder

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="CEMENT", stock_price=Decimal("25"))
    record_stock_movement(company=tenant_a, product=base["product"], warehouse=base["warehouse"], quantity=100, reason="purchase")
    client.force_login(tenant_a_owner)
    return {"client": client, "company": tenant_a, **base}


def lines(product, qty="10", price="24"):
    return {"product": [str(product.id), ""], "qty": [qty, ""], "price": [price, ""]}


def test_quotation_to_invoice_reduces_stock_and_numbers_documents(shop):
    client, product = shop["client"], shop["product"]
    response = client.post(reverse("webapp:quotation_add"), {"customer": "", "customer_name": "Doha Builders", "customer_phone": "5550",
                                                            "date": "2026-09-01", "valid_until": "2026-09-30", "notes": "Price incl. delivery",
                                                            **lines(product)})
    quotation = Quotation.objects.get(company=shop["company"])
    assert response.status_code == 302 and quotation.number == "QT-00001" and quotation.customer.name == "Doha Builders"
    page = client.get(reverse("webapp:quotation_detail", args=[quotation.id])).content.decode()
    assert "240.00" in page and "wa.me/5550" in page
    client.post(reverse("webapp:quotation_detail", args=[quotation.id]), {"action": "to_invoice"})
    invoice = SalesInvoice.objects.get(company=shop["company"])
    assert invoice.total == Decimal("240") and invoice.customer == quotation.customer
    assert product.current_stock(shop["warehouse"]) == Decimal("90")
    quotation.refresh_from_db()
    assert quotation.status == "accepted"
    assert invoice.invoice_number in client.get(reverse("webapp:sales_invoice_list")).content.decode()


def test_sales_order_partial_delivery_then_invoice(shop):
    client, product, customer = shop["client"], shop["product"], shop["customer"]
    client.post(reverse("webapp:sales_order_add"), {"customer": customer.id, "date": "2026-09-02", "reference": "PO-77", **lines(product, "10")})
    order = SalesOrder.objects.get(company=shop["company"])
    assert order.status == "confirmed" and order.number == "SO-00001"
    so_line = order.lines.get()
    client.post(reverse("webapp:sales_order_detail", args=[order.id]), {"action": "deliver", f"d_{so_line.id}": "4"})
    order.refresh_from_db()
    note = DeliveryNote.objects.get(sales_order=order)
    assert order.status == "partially_delivered" and note.number == "DN-00001"
    assert product.current_stock(shop["warehouse"]) == Decimal("96")
    assert client.get(reverse("webapp:delivery_note", args=[note.id])).status_code == 200
    client.post(reverse("webapp:sales_order_detail", args=[order.id]), {"action": "invoice"})
    assert SalesInvoice.objects.get(sales_order=order).total == Decimal("96")
    # deliver the rest and invoice it in one step; stock is not reduced twice
    client.post(reverse("webapp:sales_order_detail", args=[order.id]), {"action": "deliver_invoice", f"d_{so_line.id}": "6"})
    order.refresh_from_db()
    assert order.status == "delivered" and SalesInvoice.objects.filter(sales_order=order).count() == 2
    assert product.current_stock(shop["warehouse"]) == Decimal("90")
    # over-delivery is refused
    client.post(reverse("webapp:sales_order_detail", args=[order.id]), {"action": "deliver", f"d_{so_line.id}": "1"})
    assert DeliveryNote.objects.filter(sales_order=order).count() == 2


def test_editor_validation_and_lists(shop):
    client = shop["client"]
    client.post(reverse("webapp:quotation_add"), {"customer": "", "customer_name": "", "product": [""], "qty": [""], "price": [""]})
    assert not Quotation.objects.exists()
    for name in ("quotation_list", "sales_order_list", "sales_invoice_list", "quotation_add", "sales_order_add"):
        assert client.get(reverse(f"webapp:{name}")).status_code == 200
    other = Customer.objects.create(company=shop["company"], name="X")
    q = Quotation.objects.create(company=shop["company"], customer=other, date=date.today())
    client.post(reverse("webapp:quotation_detail", args=[q.id]), {"action": "reject"})
    q.refresh_from_db()
    assert q.status == "rejected"
