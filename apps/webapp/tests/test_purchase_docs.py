from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.purchases.models import GoodsReceiptNote, Purchase, PurchaseOrder, PurchaseReturn
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def buyer(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="FLOUR", stock_price=Decimal("20"))
    client.force_login(tenant_a_owner)
    return {"client": client, "company": tenant_a, **base}


def test_po_receive_partially_bill_and_return(buyer):
    client, product, company = buyer["client"], buyer["product"], buyer["company"]
    client.post(reverse("webapp:po_add"), {"customer": "", "customer_name": "Qatar Mills", "customer_phone": "4444",
                                           "date": "2026-09-01", "expected_date": "2026-09-05", "reference": "",
                                           "product": [str(product.id)], "qty": ["50"], "price": ["8"]})
    po = PurchaseOrder.objects.get(company=company)
    assert po.number == "PO-00001" and po.status == "confirmed" and po.supplier.name == "Qatar Mills"
    assert "wa.me/4444" in client.get(reverse("webapp:po_detail", args=[po.id])).content.decode()
    line = po.lines.get()
    client.post(reverse("webapp:po_detail", args=[po.id]), {"action": "receive", f"r_{line.id}": "30"})
    po.refresh_from_db()
    grn = GoodsReceiptNote.objects.get(purchase_order=po)
    assert po.status == "partially_received" and grn.number == "GRN-00001"
    assert product.current_stock(buyer["warehouse"]) == Decimal("30")
    assert client.get(reverse("webapp:grn_detail", args=[grn.id])).status_code == 200
    response = client.post(reverse("webapp:po_detail", args=[po.id]), {"action": "bill", "bill_number": "QM-991"})
    bill = Purchase.objects.get(purchase_order=po)
    assert response.status_code == 302 and bill.total == Decimal("240") and bill.bill_number == "QM-991"
    # receive the rest and bill it in one step
    client.post(reverse("webapp:po_detail", args=[po.id]), {"action": "receive_bill", f"r_{line.id}": "20", "bill_number": "QM-992"})
    po.refresh_from_db()
    assert po.status == "received" and Purchase.objects.filter(purchase_order=po).count() == 2
    assert product.current_stock(buyer["warehouse"]) == Decimal("50")
    # return part of the first bill
    bill_line = bill.lines.get()
    client.post(reverse("webapp:purchase_detail", args=[bill.id]), {"action": "return", f"q_{bill_line.id}": "5",
                                                                    "refund_method": "supplier_credit", "reason": "Wet bags"})
    ret = PurchaseReturn.objects.get(purchase=bill)
    assert ret.number == "PR-00001" and ret.total == Decimal("40")
    assert product.current_stock(buyer["warehouse"]) == Decimal("45")
    # can't return more than was bought
    client.post(reverse("webapp:purchase_detail", args=[bill.id]), {"action": "return", f"q_{bill_line.id}": "30"})
    assert PurchaseReturn.objects.filter(purchase=bill).count() == 1
    page = client.get(reverse("webapp:purchase_detail", args=[bill.id]))
    assert page.status_code == 200 and page.context["returned_total"] == Decimal("40")


def test_reorder_prefill_and_lists(buyer):
    client, product = buyer["client"], buyer["product"]
    product.reorder_level = 10
    product.save(update_fields=["reorder_level"])
    page = client.get(reverse("webapp:po_add"), {"reorder": "1"})
    assert page.context["rows"][0]["product"] == str(product.id) and page.context["rows"][0]["qty"] == "20"
    for name in ("po_list", "purchase_list"):
        assert client.get(reverse(f"webapp:{name}")).status_code == 200
    Supplier.objects.create(company=buyer["company"], name="S")
    client.post(reverse("webapp:po_add"), {"customer": "", "customer_name": "", "product": [""], "qty": [""], "price": [""]})
    assert not PurchaseOrder.objects.exists()
