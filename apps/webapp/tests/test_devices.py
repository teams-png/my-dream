from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.modules.models import BusinessType
from apps.inventory.models import Product
from apps.verticals.restaurant import services
from apps.verticals.restaurant.models import DiningArea, DiningTable

pytestmark = pytest.mark.django_db


@pytest.fixture
def restaurant(tenant_a, tenant_a_owner, sales_fixtures_factory):
    call_command("seed_platform")
    tenant_a.business_type = BusinessType.objects.get(code="restaurant")
    tenant_a.save(update_fields=["business_type"])
    base = sales_fixtures_factory(tenant_a, sku="X-ING", stock_price=Decimal("1"))
    burger = Product.objects.create(company=tenant_a, sku="BURGER", name="Burger", unit=base["unit"],
                                    selling_price=20, is_stock_tracked=False, tracking_type="none")
    table = DiningTable.objects.create(company=tenant_a, area=DiningArea.objects.create(company=tenant_a, name="Hall"), name="T9")
    return {**base, "burger": burger, "table": table, "user": tenant_a_owner}


def test_device_pages_render(client, restaurant):
    client.force_login(restaurant["user"])
    assert b"Receipt printer" in client.get(reverse("webapp:devices")).content
    assert b"BroadcastChannel" in client.get(reverse("webapp:customer_display")).content


def test_kot_and_receipt_print_data(client, tenant_a, restaurant):
    d = restaurant
    order = services.create_order(company=tenant_a, channel="dine_in", table=d["table"], waiter=d["user"], guests=2)
    services.add_order_line(company=tenant_a, order=order, product=d["burger"], quantity=2, notes="no onion")
    first = services.send_to_kitchen(company=tenant_a, order=order)
    services.add_order_line(company=tenant_a, order=order, product=d["burger"], quantity=1)
    second = services.send_to_kitchen(company=tenant_a, order=order)
    client.force_login(d["user"])
    kot1 = client.get(reverse("webapp:device_kot", args=[first.id])).json()
    kot2 = client.get(reverse("webapp:device_kot", args=[second.id])).json()
    assert kot1["lines"] == [{"qty": "2", "name": "Burger", "extra": ["NOTE: no onion"]}]
    assert kot2["lines"][0]["qty"] == "1" and any("ROUND 2" in m for m in kot2["meta"])
    assert "TABLE T9" in kot1["meta"] and "GUESTS 2" in kot1["meta"]
    receipt = client.get(reverse("webapp:device_restaurant_receipt", args=[order.id])).json()
    assert receipt["grand_total"] == "60.00" and len(receipt["lines"]) == 2


def test_print_data_is_tenant_scoped(client, tenant_a, tenant_b, restaurant):
    from apps.tenants.models import CompanyMembership
    d = restaurant
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    outsider = CompanyMembership.objects.filter(company=tenant_b).first().user
    client.force_login(outsider)
    assert client.get(reverse("webapp:device_restaurant_receipt", args=[order.id])).status_code == 404


def test_print_agent_rejects_public_hosts():
    import importlib.util, io, pathlib
    spec = importlib.util.spec_from_file_location("print_agent", pathlib.Path("scripts/print_agent.py"))
    agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)

    class Fake(agent.Handler):
        def __init__(self, headers, body=b"x"):
            self.headers = headers; self.path = "/print"; self.rfile = io.BytesIO(body); self.wfile = io.BytesIO()
            self.request_version = "HTTP/1.1"; self.requestline = "POST /print HTTP/1.1"; self.client_address = ("127.0.0.1", 0)
            self.command = "POST"
        def log_message(self, *a): pass
    h = Fake({"X-Printer-Host": "8.8.8.8", "X-Printer-Port": "9100", "Content-Length": "1"})
    h.do_POST()
    assert b"only printers on the local network" in h.wfile.getvalue()


def test_invoice_share_link_whatsapp_and_email(client, tenant_a, restaurant, mailoutbox=None):
    from django.core import mail
    from apps.sales import sharing
    d = restaurant
    tenant_a.country = "Qatar"; tenant_a.save(update_fields=["country"])
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    services.add_order_line(company=tenant_a, order=order, product=d["burger"], quantity=1)
    invoice = services.settle_order(company=tenant_a, user=d["user"], order=order, warehouse=d["warehouse"],
                                    date=order.created_at.date(), payments=[{"method": "cash", "amount": Decimal("20")}])
    invoice.customer.phone = "5555 1234"; invoice.customer.save(update_fields=["phone"])
    client.force_login(d["user"])
    page = client.get(reverse("webapp:invoice_share", args=[invoice.id]))
    assert page.status_code == 200
    assert "https://wa.me/97455551234?text=" in page.context["whatsapp_url"]
    public_url = page.context["public_url"]
    # the public link works without login and cannot be forged
    client.logout()
    public = client.get(public_url)
    assert public.status_code == 200 and invoice.invoice_number.encode() in public.content
    assert client.get(reverse("webapp:public_invoice", args=["forged-token"])).status_code == 404
    other = sharing.share_token(invoice).replace(str(invoice.id), str(invoice.id + 1))
    assert client.get(reverse("webapp:public_invoice", args=[other])).status_code == 404
    client.force_login(d["user"])
    resp = client.post(reverse("webapp:invoice_share", args=[invoice.id]), {"email": "guest@example.com", "note": "Thanks!"})
    assert resp.status_code == 302
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["guest@example.com"]
    assert invoice.invoice_number in mail.outbox[0].subject and len(mail.outbox[0].attachments) == 1


def test_phone_normalisation():
    from apps.sales.sharing import normalise_phone
    assert normalise_phone("+91 98470 12345") == "919847012345"
    assert normalise_phone("098470 12345", "India") == "919847012345"
    assert normalise_phone("0097455551234") == "97455551234"
    assert normalise_phone("", "Qatar") == ""
