import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_zatca_payload_matches_official_example():
    from apps.sales.einvoice import zatca_payload
    payload = zatca_payload(seller="Bobs Records", vat_number="310122393500003",
                            timestamp="2022-04-25T15:30:00Z", total=Decimal("1000.00"), vat_total=Decimal("150.00"))
    assert payload == "AQxCb2JzIFJlY29yZHMCDzMxMDEyMjM5MzUwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoEBzEwMDAuMDAFBjE1MC4wMA=="


def test_invoice_shows_zatca_qr_only_for_saudi_vat_companies(tenant_a, tenant_a_owner, sales_fixtures_factory):
    from apps.sales.services import create_invoice
    d = sales_fixtures_factory(tenant_a)
    invoice = create_invoice(company=tenant_a, user=tenant_a_owner, customer=d["customer"], date=date(2026, 9, 1),
                             lines=[{"product": d["product"], "quantity": 1, "unit_price": Decimal("100")}],
                             warehouse=d["warehouse"], tax_rate=Decimal("0.15"))
    from apps.sales.sharing import render_invoice_html
    assert "Simplified tax invoice" not in render_invoice_html(invoice)
    tenant_a.country, tenant_a.vat_number = "Saudi Arabia", "310122393500003"
    tenant_a.save(update_fields=["country", "vat_number"])
    invoice.refresh_from_db()
    html = render_invoice_html(invoice)
    assert "Simplified tax invoice" in html and "<svg" in html and "310122393500003" in html


def test_owner_can_export_everything_and_others_cannot(client, tenant_a, tenant_b, tenant_a_owner, sales_fixtures_factory):
    from apps.tenants.models import CompanyMembership
    sales_fixtures_factory(tenant_a)
    sales_fixtures_factory(tenant_b, sku="B-1")
    client.force_login(tenant_a_owner)
    resp = client.post(reverse("webapp:export_data"))
    assert resp.status_code == 200 and resp["Content-Type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["tables"]["inventory.Product"] == 1 and "accounts.User" not in manifest["tables"]
    products = json.loads(archive.read("data/inventory.Product.json"))
    assert all(p["fields"]["company"] == tenant_a.id for p in products)  # nothing from tenant B
    member = CompanyMembership.objects.filter(company=tenant_a).exclude(role__name="Owner").first()
    if member:
        client.force_login(member.user)
        assert client.post(reverse("webapp:export_data")).status_code == 302


def test_api_docs_require_login(client, tenant_a_owner):
    assert client.get("/api/docs/").status_code in (401, 403)
    client.force_login(tenant_a_owner)
    assert client.get("/api/docs/").status_code == 200
    schema = client.get("/api/schema/")
    assert schema.status_code == 200 and b"/api/sales/" in schema.content
