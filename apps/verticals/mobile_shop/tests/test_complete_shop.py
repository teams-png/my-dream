from datetime import date
from decimal import Decimal

import pytest
from django.template.loader import get_template
from django.urls import reverse

from apps.sales.services import create_invoice
from apps.verticals.mobile_shop.models import (
    MobileInstallmentPlan, MobileRepairPart, MobileUnit, MobileWarrantyClaim,
)
from apps.verticals.mobile_shop.services import record_installment_payment
from apps.webapp.forms import MobileBulkIMEIForm, MobileProductForm


pytestmark = pytest.mark.django_db


def test_mobile_product_form_stores_specs_and_uses_imei_stock(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="FORM-BASE")
    form = MobileProductForm({
        "sku": "PHONE-5G", "name": "Phone 5G", "unit": f["unit"].id,
        "cost_price": "500", "selling_price": "650", "reorder_level": "1",
        "item_type": "handset", "model_number": "P5", "ram": "8GB",
        "storage": "256GB", "network": "5G", "battery": "5000mAh",
    }, company=tenant_a)
    assert form.is_valid(), form.errors
    product = form.save(commit=False); product.company = tenant_a; product.save()
    assert product.attributes["storage"] == "256GB"
    assert product.is_stock_tracked is False


def test_bulk_imei_form_parses_rows(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="BULK-PHONE")
    f["product"].attributes = {"item_type": "handset"}; f["product"].save(update_fields=["attributes"])
    form = MobileBulkIMEIForm({
        "product": f["product"].id, "warehouse": f["warehouse"].id,
        "purchase_price": "400", "warranty_months": "12", "condition": "new",
        "imeis": "111111111111111,SN1\n222222222222222,SN2",
    }, company=tenant_a)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["imeis"][1] == ("222222222222222", "SN2")


def test_warranty_and_repair_parts_keep_imei_history(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="WARRANTY-PHONE")
    unit = MobileUnit.objects.create(company=tenant_a, product=f["product"], imei="333333333333333",
        purchase_price=400, sold_price=550, sold_date=date.today(), buyer=f["customer"], warranty_months=12, status="sold")
    claim = MobileWarrantyClaim.objects.create(company=tenant_a, claim_number="WAR-000001", unit=unit,
        customer=f["customer"], issue="No power", received_date=date.today())
    assert claim.unit.warranty_expires is not None


def test_installment_collection_updates_invoice_and_plan(tenant_a, tenant_a_owner, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="INST-PHONE")
    invoice = create_invoice(company=tenant_a, user=tenant_a_owner, customer=f["customer"], date=date.today(),
        warehouse=f["warehouse"], lines=[{"product": f["product"], "quantity": 1, "unit_price": Decimal("600")}])
    plan = MobileInstallmentPlan.objects.create(company=tenant_a, invoice=invoice, customer=f["customer"],
        financed_amount=Decimal("600"), installment_count=3, next_due_date=date.today())
    record_installment_payment(company=tenant_a, user=tenant_a_owner, plan=plan,
        amount=Decimal("200"), date=date.today(), method="cash")
    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("200")
    assert plan.outstanding == Decimal("400")


def test_mobile_pages_and_pos_include_complete_workflows():
    for name in ("mobile_repair_list", "mobile_warranty_list", "mobile_tradein_list", "mobile_installment_list"):
        assert reverse(f"webapp:{name}")
    source = get_template("webapp/pos.html").template.source
    assert "mobile_unit_id" in source
    assert "installment_count" in source
