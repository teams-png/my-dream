"""Pharmacy: a purchase brings in a batch with its expiry; the billing screen finds a medicine by its salt name, sells
the batch that expires first and prints batch + expiry on the bill; ℞ medicines carry the doctor's details into the
prescription register."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.industry.models import PrescriptionSale
from apps.inventory.models import Product, ProductBatch, Unit
from apps.sales.models import SalesInvoiceLine
from apps.sales.sharing import render_invoice_html
from apps.suppliers.models import Supplier
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def test_purchase_batch_fefo_bill_and_prescription_register(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Care Pharmacy", "business_type": "medical_shop", "country": "India", "full_name": "Anas",
        "email": "a@rx.test", "phone": "", "password": "Care-Pharma-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="a@rx.test")
    unit, _ = Unit.objects.get_or_create(company=company, name="strip")
    amox = Product.objects.create(company=company, sku="AMX-500", name="Mox 500 capsule", unit=unit,
                                  selling_price=Decimal("110"), tracking_type="batch",
                                  attributes={"generic_name": "Amoxicillin", "strength": "500 mg", "prescription_required": True})
    supplier = Supplier.objects.create(company=company, name="Malabar Pharma Distributors")
    today = timezone.localdate()
    for number, months, qty in (("MX2611", 14, "20"), ("MX2504", 3, "5")):
        r = client.post(reverse("webapp:purchase_add"), {
            "supplier": supplier.id, "product": amox.id, "quantity": qty, "unit_cost": "72", "bill_number": f"MPD-{number}",
            "date": today.isoformat(), "batch_number": number, "expiry_date": (today + timedelta(days=30 * months)).isoformat()})
        assert r.status_code == 302, r.content
    assert ProductBatch.objects.filter(company=company, product=amox).count() == 2
    data = client.get(reverse("webapp:pos")).context["pos_data"]
    item = next(p for p in data["products"] if p["id"] == amox.id)
    assert data["pharmacy"] and item["rx"] and item["variant"] == "Amoxicillin 500 mg" and item["stock"] == "25"
    assert item["exp"] == f"{today + timedelta(days=90):%m/%y}"

    r = client.post(reverse("webapp:pos_checkout"), json.dumps({"payment_method": "cash", "lines": [
        {"product_id": amox.id, "quantity": 2, "unit_price": "110"}], "prescription": {
        "doctor": "Dr. Nazeer Ahmed", "reg": "KMC 45120", "number": "RX-778", "patient": "Leela Devi", "age": "72"}}),
        content_type="application/json")
    assert r.status_code == 200, r.content
    line = SalesInvoiceLine.objects.select_related("batch").get(invoice_id=r.json()["invoice_id"])
    assert line.batch.batch_number == "MX2504"  # the one that expires first
    bill = render_invoice_html(line.invoice)
    assert "Batch <b>MX2504</b>" in bill and "Dr. Nazeer Ahmed" in bill and "KMC 45120" in bill and "Leela Devi" in bill
    receipt = client.get(f"/devices/print/invoice/{line.invoice_id}.json").json()
    assert receipt["lines"][0]["extra"][0].startswith("Batch MX2504 Exp") and "Dr. Nazeer Ahmed" in receipt["meta"]
    assert PrescriptionSale.objects.get(invoice=line.invoice).rx_number == "RX-778"
    page = client.get(reverse("webapp:prescription_register")).content.decode()
    assert "Leela Devi" in page and "Dr. Nazeer Ahmed" in page and "MX2504" in page and "RX-778" in page
    assert "Leela" not in client.get(reverse("webapp:prescription_register") + "?q=George").content.decode()
