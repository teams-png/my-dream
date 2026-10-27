"""Serial-numbered items (a computer shop's laptops and printers) are picked by serial number at the POS: the serial
is marked sold, and the bill and the receipt show it with the warranty."""
import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.industry.common import default_warehouse
from apps.inventory.models import Product, ProductSerial, Unit
from apps.inventory.services import register_serial
from apps.sales.models import SalesInvoiceLine
from apps.sales.sharing import render_invoice_html
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def test_pos_sells_a_laptop_by_serial_number(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "PC World", "business_type": "computer_shop", "country": "India", "full_name": "Ajmal",
        "email": "a@pc.test", "phone": "", "password": "Pc-World-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="a@pc.test")
    unit, _ = Unit.objects.get_or_create(company=company, name="pcs")
    laptop = Product.objects.create(company=company, sku="LT-1", name="HP 15s i5 laptop", unit=unit,
                                    selling_price=Decimal("52000"), tracking_type="serial",
                                    attributes={"warranty_months": 12})
    wh = default_warehouse(company)
    for sn in ("5CD123A", "5CD123B"):
        register_serial(company=company, product=laptop, warehouse=wh, serial_number=sn)
    data = client.get(reverse("webapp:pos")).context["pos_data"]
    item = next(p for p in data["products"] if p["id"] == laptop.id)
    assert item["serial"] is True and item["stock"] == "2" and [u["imei"] for u in item["mobile_units"]] == ["5CD123A", "5CD123B"]
    serial = ProductSerial.objects.get(company=company, serial_number="5CD123B")
    r = client.post(reverse("webapp:pos_checkout"), json.dumps({"payment_method": "cash", "lines": [
        {"product_id": laptop.id, "quantity": 1, "unit_price": "52000", "serial_id": serial.id}]}),
        content_type="application/json")
    assert r.status_code == 200, r.content
    serial.refresh_from_db()
    line = SalesInvoiceLine.objects.get(invoice_id=r.json()["invoice_id"])
    assert serial.status == "sold" and line.serial_id == serial.id
    bill = render_invoice_html(line.invoice)
    assert "5CD123B" in bill and "Warranty: 12 months (from the bill date)" in bill
    receipt = client.get(f"/devices/print/invoice/{line.invoice_id}.json").json()
    assert receipt["lines"][0]["extra"] == ["S/N 5CD123B"]
    # the same serial cannot be sold twice
    r = client.post(reverse("webapp:pos_checkout"), json.dumps({"payment_method": "cash", "lines": [
        {"product_id": laptop.id, "quantity": 1, "unit_price": "52000", "serial_id": serial.id}]}),
        content_type="application/json")
    assert r.status_code == 400 and "5CD123B" in r.json()["error"]
    left = next(p for p in client.get(reverse("webapp:pos")).context["pos_data"]["products"] if p["id"] == laptop.id)
    assert [u["imei"] for u in left["mobile_units"]] == ["5CD123A"]
