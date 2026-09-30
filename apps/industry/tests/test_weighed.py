import json
import uuid
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.industry.models import ScaleSettings
from apps.inventory.models import Product, Unit
from apps.inventory.services import record_stock_movement
from apps.industry.common import default_warehouse
from apps.sales.models import SalesInvoiceLine
from apps.tenants.models import Company
from apps.webapp.forms import BusinessProductForm

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Fresh Fish", "business_type": "fish_meat_shop", "country": "Qatar", "full_name": "Omar K",
        "email": "o@fish.test", "phone": "", "password": "Fresh-Fish-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="o@fish.test")
    unit, _ = Unit.objects.get_or_create(company=company, name="kg")
    hamour = Product.objects.create(company=company, sku="HAM", name="Hamour", unit=unit, selling_price=Decimal("48.00"),
                                    attributes={"sold_by_weight": True, "scale_code": "123"})
    record_stock_movement(company=company, product=hamour, warehouse=default_warehouse(company),
                          quantity=Decimal("20"), reason="adjustment", reference="opening")
    return {"company": company, "hamour": hamour, "unit": unit, "client": client}


def _other_shop(client):
    client.logout()
    client.post(reverse("webapp:signup"), {
        "business_name": "Gadget Hub", "business_type": "electronics_store", "country": "Qatar", "full_name": "Ali R",
        "email": "a@gadget.test", "phone": "", "password": "Gadget-Hub-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email="a@gadget.test")


def test_product_form_has_weight_fields_only_for_fresh_food(shop):
    form = BusinessProductForm(company=shop["company"])
    assert "sold_by_weight" in form.fields and "scale_code" in form.fields
    assert "sold_by_weight" not in BusinessProductForm(company=_other_shop(shop["client"])).fields
    form = BusinessProductForm({"sku": "LAMB", "name": "Lamb", "unit": shop["unit"].id, "cost_price": "20",
                                "selling_price": "42", "reorder_level": "0", "sold_by_weight": "on", "scale_code": "00456"},
                               company=shop["company"])
    assert form.is_valid(), form.errors
    product = form.save(commit=False)
    product.company = shop["company"]
    product.save()
    assert product.attributes["sold_by_weight"] is True and product.attributes["scale_code"] == "456"


def test_pos_gets_scale_settings_and_weighed_flag(shop):
    c = shop["client"]
    page = c.get(reverse("webapp:pos"))
    data = page.context["pos_data"]
    assert data["scale"] == {"prefixes": [str(n) for n in range(20, 30)], "codeDigits": 5, "valueType": "weight", "decimals": 3}
    hamour = next(p for p in data["products"] if p["sku"] == "HAM")
    assert hamour["weighed"] is True and hamour["plu"] == "123"
    assert b"weighDialog" in page.content


def test_fractional_kg_sale_books_exact_weight(shop):
    c = shop["client"]
    resp = c.post(reverse("webapp:pos_checkout"), json.dumps({
        "client_id": str(uuid.uuid4()), "payment_method": "cash",
        "lines": [{"product_id": shop["hamour"].id, "quantity": 0.7534, "unit_price": "48.00"}]}),
        content_type="application/json")
    assert resp.status_code == 200, resp.content
    line = SalesInvoiceLine.objects.get(invoice_id=resp.json()["invoice_id"])
    assert line.quantity == Decimal("0.753")
    assert resp.json()["total"] == "36.14"  # 0.753 x 48 = 36.144
    assert shop["hamour"].current_stock() == Decimal("19.247")


def test_scale_settings_page(shop):
    c = shop["client"]
    page = c.get(reverse("webapp:scale_settings"))
    assert page.status_code == 200 and page.context["example"]["barcode"] == "2000123012506"
    bad = c.post(reverse("webapp:scale_settings"), {"prefixes": "2a", "code_digits": 5, "value_type": "weight", "value_decimals": 3})
    assert bad.status_code == 200 and bad.context["form"].errors
    ok = c.post(reverse("webapp:scale_settings"), {"prefixes": "22, 23", "code_digits": 4, "value_type": "price", "value_decimals": 2})
    assert ok.status_code == 302
    cfg = ScaleSettings.load(shop["company"])
    assert cfg.as_dict() == {"prefixes": ["22", "23"], "codeDigits": 4, "valueType": "price", "decimals": 2}


def test_scale_page_hidden_for_other_types(shop):
    _other_shop(shop["client"])
    assert shop["client"].get(reverse("webapp:scale_settings")).status_code == 302
