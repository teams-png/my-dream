"""Today page: today's numbers, late payers with a WhatsApp reminder, and documents running out."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.employees.models import Employee, EmployeeDocument
from apps.sales.models import SalesInvoice

pytestmark = pytest.mark.django_db


def test_today_page(tenant_a, tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    today = timezone.localdate()
    cust = Customer.objects.create(company=tenant_a, name="Ravi Kumar", phone="+974 5551 2345")
    SalesInvoice.objects.create(company=tenant_a, customer=cust, invoice_number="INV-9", date=today - timedelta(days=40),
                                due_date=today - timedelta(days=10), subtotal=Decimal("500"), total=Decimal("500"),
                                amount_paid=Decimal("200"), status="partial")
    emp = Employee.objects.create(company=tenant_a, name="Anu")
    EmployeeDocument.objects.create(company=tenant_a, employee=emp, document_type="ID / residence card",
                                    document_number="1", expiry_date=today + timedelta(days=5))
    assert reverse("webapp:today") in c.get(reverse("webapp:dashboard")).content.decode()
    page = c.get(reverse("webapp:today")).content.decode()
    assert "Ravi Kumar" in page and "10 days late" in page and "300.00" in page and "wa.me/97455512345" in page
    assert "Anu" in page and "Expiring soon" in page


def test_bell_feed_and_suggestions(tenant_a, tenant_a_owner):
    from apps.notifications.models import Notification
    c = Client()
    c.force_login(tenant_a_owner)
    Notification.objects.create(company=tenant_a, recipient=tenant_a_owner, title="Low stock: Cable", message="2 left")
    Notification.objects.create(company=tenant_a, title="Read one", is_read=True)
    data = c.get(reverse("webapp:notification_feed")).json()
    assert data["unread"] == 1 and [i["title"] for i in data["items"]] == ["Read one", "Low stock: Cable"] or \
        {i["title"] for i in data["items"]} == {"Read one", "Low stock: Cable"}
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "data-bell" in page and "data-pin" in page and "js/topbar.js" in page
    assert "Suggestions for today" not in page  # nothing worth suggesting yet
    today = timezone.localdate()
    cust = Customer.objects.create(company=tenant_a, name="Old Friend", phone="5550")
    SalesInvoice.objects.create(company=tenant_a, customer=cust, invoice_number="INV-1", date=today - timedelta(days=90),
                                due_date=today - timedelta(days=60), subtotal=Decimal("50"), total=Decimal("50"),
                                status="unpaid")
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Suggestions for today" in page and "Invoices past their due date: 1" in page
    assert "bought in 2 months: 1" in page
