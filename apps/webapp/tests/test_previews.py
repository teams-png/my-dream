"""Preview panel: invoice and customer details open beside the list (only this business's records)."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.inventory.models import Product, Unit
from apps.sales.models import SalesInvoice, SalesInvoiceLine

pytestmark = pytest.mark.django_db


def test_invoice_and_customer_preview(tenant_a, tenant_a_owner, tenant_b):
    c = Client()
    c.force_login(tenant_a_owner)
    cust = Customer.objects.create(company=tenant_a, name="Ravi Kumar", phone="+974 5551 2345")
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    prod = Product.objects.create(company=tenant_a, sku="C1", name="USB Cable", unit=unit)
    inv = SalesInvoice.objects.create(company=tenant_a, customer=cust, invoice_number="INV-77", date=date(2026, 10, 1),
                                      subtotal=Decimal("30"), total=Decimal("30"), amount_paid=Decimal("10"),
                                      status="partial")
    SalesInvoiceLine.objects.create(invoice=inv, product=prod, quantity=Decimal("2"), unit_price=Decimal("15"),
                                    line_total=Decimal("30"))
    assert reverse("webapp:invoice_preview", args=[inv.id]) in c.get(reverse("webapp:sales_invoice_list")).content.decode()
    assert reverse("webapp:customer_preview", args=[cust.id]) in c.get(reverse("webapp:customer_list")).content.decode()

    html = c.get(reverse("webapp:invoice_preview", args=[inv.id])).content.decode()
    assert "INV-77" in html and "USB Cable" in html and "20.00" in html and "wa.me/97455512345" in html
    html = c.get(reverse("webapp:customer_preview", args=[cust.id])).content.decode()
    assert "Ravi Kumar" in html and "INV-77" in html and "Owes 30.00" in html  # balance comes from payments recorded

    other = Customer.objects.create(company=tenant_b, name="Not mine")
    assert c.get(reverse("webapp:customer_preview", args=[other.id])).status_code == 404
