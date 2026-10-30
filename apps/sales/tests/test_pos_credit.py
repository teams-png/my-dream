"""Hardware and other trade shops can sell on credit at the counter (contractor accounts)."""
import json
import uuid
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry.common import default_warehouse
from apps.inventory.models import Product, Unit
from apps.inventory.services import record_stock_movement
from apps.sales.models import SalesInvoice
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _shop(client, code, email):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Shop " + code, "business_type": code, "country": "India", "full_name": "Anil K",
        "email": email, "phone": "", "password": "Shop-Counter-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email)


def test_hardware_pos_sells_on_credit_to_a_contractor(client):
    company = _shop(client, "hardware_store", "a@hw.test")
    unit, _ = Unit.objects.get_or_create(company=company, name="pcs")
    nails = Product.objects.create(company=company, sku="N1", name="Concrete pin", unit=unit, selling_price=Decimal("500"))
    record_stock_movement(company=company, product=nails, warehouse=default_warehouse(company), quantity=Decimal("10"),
                          reason="adjustment", reference="opening")
    contractor = Customer.objects.create(company=company, name="Shihab (contractor)", phone="9847000000")
    page = client.get(reverse("webapp:pos")).content.decode()
    assert 'data-method="credit"' in page and 'data-method="installment"' not in page
    resp = client.post(reverse("webapp:pos_checkout"), json.dumps({
        "client_id": str(uuid.uuid4()), "payment_method": "credit", "customer_id": contractor.id,
        "amount_paid": "200", "deposit_method": "cash",
        "lines": [{"product_id": nails.id, "quantity": 2, "unit_price": "500"}]}), content_type="application/json")
    assert resp.status_code == 200, resp.content
    inv = SalesInvoice.objects.get(pk=resp.json()["invoice_id"])
    assert inv.customer == contractor and inv.total == Decimal("1000") and inv.amount_paid == Decimal("200")


def test_shops_without_credit_sales_do_not_show_it(client):
    _shop(client, "saloon", "s@salon.test")
    assert 'data-method="credit"' not in client.get(reverse("webapp:pos")).content.decode()
