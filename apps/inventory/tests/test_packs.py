"""Packs: buy a carton of 24, sell a carton or single pieces; stock is always counted in pieces —
purchases, POS, returns, purchase orders / goods receipt and purchase returns all move pack × pieces."""
import uuid
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import ProductPack
from apps.purchases import services as purchases
from apps.sales import pos
from apps.sales import services as sales
from apps.sales.models import SalesInvoice
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a, sku="WATER-500")  # selling 10 / piece
    product = data["product"]
    carton = ProductPack.objects.create(company=tenant_a, product=product, name="Carton", factor=Decimal("24"),
                                        barcode="CTN-WATER", selling_price=Decimal("200"))
    supplier = Supplier.objects.create(company=tenant_a, name="Al Rawabi")
    return {**data, "company": tenant_a, "user": tenant_a_owner, "carton": carton, "supplier": supplier}


def _stock(shop):
    shop["product"].refresh_from_db()
    return shop["product"].current_stock()


def test_buy_cartons_sell_carton_and_pieces_and_return(shop):
    company, user, product, carton = shop["company"], shop["user"], shop["product"], shop["carton"]
    bill = purchases.create_purchase(company=company, user=user, supplier=shop["supplier"], date=timezone.localdate(),
                                     warehouse=shop["warehouse"], lines=[{"product": product, "pack": carton,
                                                                          "quantity": Decimal("2"), "unit_cost": Decimal("120")}])
    line = bill.lines.get()
    assert _stock(shop) == Decimal("48") and line.unit_name == "Carton" and line.line_total == Decimal("240")
    assert line.unit_label == " — Carton (24)"

    result = pos.checkout(company=company, user=user, payload={
        "client_id": str(uuid.uuid4()), "payment_method": "cash", "created_at": timezone.now().isoformat(),
        "lines": [{"product_id": product.id, "pack_id": carton.id, "quantity": 1, "unit_price": "200.00"},
                  {"product_id": product.id, "quantity": 3, "unit_price": "10.00"}]})
    invoice = SalesInvoice.objects.get(id=result["invoice_id"])
    assert invoice.total == Decimal("230") and _stock(shop) == Decimal("21")
    pack_line = invoice.lines.get(unit_name="Carton")
    assert pack_line.quantity == 1 and pack_line.unit_factor == Decimal("24")

    sales.process_return(company=company, user=user, invoice=invoice, date=timezone.localdate(),
                         warehouse=shop["warehouse"], lines=[{"product": product, "quantity": Decimal("1"),
                                                              "unit_price": Decimal("200"), "unit_name": "Carton",
                                                              "unit_factor": Decimal("24")}])
    assert _stock(shop) == Decimal("45")

    purchases.process_purchase_return(company=company, user=user, purchase=bill, date=timezone.localdate(),
                                      warehouse=shop["warehouse"], lines=[{"product": product, "quantity": Decimal("1"),
                                                                           "unit_cost": Decimal("120"), "unit_name": "Carton",
                                                                           "unit_factor": Decimal("24")}])
    assert _stock(shop) == Decimal("21")


def test_purchase_order_by_carton_and_goods_receipt(shop):
    company, user, product, carton = shop["company"], shop["user"], shop["product"], shop["carton"]
    client = Client()
    client.force_login(user)
    page = client.get(reverse("webapp:po_add")).content.decode()
    assert f'"{product.id}:{carton.id}"' in page and "Carton (24)" in page
    client.post(reverse("webapp:po_add"), {"customer": shop["supplier"].id,
                                            "date": timezone.localdate().isoformat(), "product": [f"{product.id}:{carton.id}"],
                                            "qty": ["3"], "price": ["120"]})
    from apps.purchases.models import PurchaseOrder
    po = PurchaseOrder.objects.get(company=company)
    po_line = po.lines.get()
    assert po_line.unit_name == "Carton" and po_line.quantity == 3
    purchases.create_goods_receipt(company=company, user=user, purchase_order=po, warehouse=shop["warehouse"],
                                   date=timezone.localdate(), lines=[{"po_line": po_line, "quantity": Decimal("2")}])
    assert _stock(shop) == Decimal("48")


def test_pack_screen_pos_catalog_and_rules(shop, tenant_b, sales_fixtures_factory):
    company, product = shop["company"], shop["product"]
    client = Client()
    client.force_login(shop["user"])
    url = reverse("webapp:product_pack_action", args=[product.id])
    client.post(url, {"do": "save", "name": "Box", "factor": "6", "barcode": "", "selling_price": "", "cost_price": ""})
    box = ProductPack.objects.get(company=company, name="Box")
    assert box.price == (6 * product.selling_price).quantize(Decimal("0.01"))  # pieces × piece price when left empty
    client.post(url, {"do": "save", "name": "Pallet", "factor": "1", "barcode": ""})  # 1 piece is not a pack
    client.post(url, {"do": "save", "name": "Crate", "factor": "12", "barcode": "WATER-500"})  # clashes with the SKU
    assert not ProductPack.objects.filter(company=company, name__in=["Pallet", "Crate"]).exists()
    page = client.get(reverse("webapp:product_edit", args=[product.id])).content.decode()
    assert "Cartons, boxes" in page and "CTN-WATER" in page
    pos_page = client.get(reverse("webapp:pos")).content.decode()
    assert '"barcode": "CTN-WATER"' in pos_page and '"factor": "24"' in pos_page
    client.post(url, {"do": "delete", "pack_id": box.id})
    assert not ProductPack.objects.filter(pk=box.pk).exists()

    other = sales_fixtures_factory(tenant_b, sku="B-1")
    with pytest.raises(pos.PosError):  # a pack must belong to the product being sold
        pos.checkout(company=company, user=shop["user"], payload={
            "client_id": str(uuid.uuid4()), "payment_method": "cash",
            "lines": [{"product_id": product.id, "pack_id": ProductPack.objects.create(
                company=tenant_b, product=other["product"], name="Carton", factor=Decimal("12")).id,
                "quantity": 1, "unit_price": "10.00"}]})
