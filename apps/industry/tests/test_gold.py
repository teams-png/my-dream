from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.industry import gold as svc
from apps.industry.models import GoldRate
from apps.inventory.models import Product, Unit
from apps.modules.models import BusinessType
from apps.tenants.models import Company
from apps.webapp.forms import BusinessProductForm

pytestmark = pytest.mark.django_db


def signup(client, code, email):
    client.post(reverse("webapp:signup"), {
        "business_name": f"Shop {code}", "business_type": code, "country": "Qatar", "full_name": "Test Owner",
        "email": email, "phone": "", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email)


@pytest.fixture
def jeweller(client):
    call_command("seed_platform")
    company = signup(client, "jewelry_shop", "g@gold.test")
    return {"company": company, "user": company.memberships.first().user, "client": client}


def ring(company, **attrs):
    unit = Unit.objects.for_company(company).first() or Unit.objects.create(company=company, name="pcs")
    base = {"weight_grams": "10", "purity": "22K", "making_mode": "per_gram", "making_charge": "15"}
    base.update(attrs)
    return Product.objects.create(company=company, sku=f"R{Product.objects.count() + 1}", name="Ring", unit=unit,
                                  cost_price=0, selling_price=Decimal("100"), attributes=base)


def test_breakdown_modes():
    rates = {"22K": Decimal("250")}
    per_gram = svc.breakdown({"weight_grams": "10", "purity": "22k", "making_charge": "15", "stone_value": "40"}, rates)
    assert (per_gram["gold"], per_gram["making"], per_gram["stones"], per_gram["total"]) == (
        Decimal("2500.00"), Decimal("150.00"), Decimal("40.00"), Decimal("2690.00"))
    fixed = svc.breakdown({"weight_grams": "10", "purity": "22K", "making_mode": "fixed", "making_charge": "99"}, rates)
    assert fixed["total"] == Decimal("2599.00")
    percent = svc.breakdown({"weight_grams": "10", "purity": "22K", "making_mode": "percent", "making_charge": "8"}, rates)
    assert percent["making"] == Decimal("200.00") and percent["total"] == Decimal("2700.00")
    assert svc.breakdown({"weight_grams": "10", "purity": "18K"}, rates) is None  # no rate for the karat
    assert svc.breakdown({"purity": "22K"}, rates) is None
    assert svc.breakdown(None, rates) is None


def test_set_rates_latest_wins_and_rejects_zero(jeweller):
    company, user = jeweller["company"], jeweller["user"]
    svc.set_rates(company, user, {"22K": "250", "24K": "", "BAD": "9"})
    svc.set_rates(company, user, {"22K": "255.5"})
    assert GoldRate.objects.for_company(company).count() == 1
    assert svc.current_rates(company) == {"22K": Decimal("255.50")}
    with pytest.raises(ValueError):
        svc.set_rates(company, user, {"18K": "0"})


def test_apply_to_products_and_pos_price(jeweller):
    company, user = jeweller["company"], jeweller["user"]
    item = ring(company)
    plain = ring(company, weight_grams="")
    svc.set_rates(company, user, {"22K": "250"})
    from apps.webapp.views import _pos_catalog
    catalog, _ = _pos_catalog(company)
    by_id = {c["id"]: c for c in catalog}
    assert by_id[item.id]["price"] == "2650.00" and "22K" in by_id[item.id]["variant"]
    assert by_id[plain.id]["price"] == "100.00"
    assert svc.apply_to_products(company) == 1
    item.refresh_from_db()
    assert item.selling_price == Decimal("2650.00")
    assert svc.apply_to_products(company) == 0


def test_gold_page_saves_rates_and_updates_prices(jeweller):
    client, company = jeweller["client"], jeweller["company"]
    item = ring(company)
    assert client.get(reverse("webapp:gold_rates")).status_code == 200
    response = client.post(reverse("webapp:gold_rates"), {"rate_22K": "260", "apply": "on"})
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.selling_price == Decimal("2750.00")
    page = client.get(reverse("webapp:gold_rates")).content.decode()
    assert "2750.00" in page
    client.post(reverse("webapp:gold_rates"), {"rate_22K": "-5"})
    assert svc.current_rates(company)["22K"] == Decimal("260.00")


def test_other_business_types_cannot_open_gold_page(client):
    call_command("seed_platform")
    signup(client, "grocery_store", "x@grocery.test")
    response = client.get(reverse("webapp:gold_rates"))
    assert response.status_code == 302


def test_product_form_saves_industry_fields_for_every_type(jeweller):
    """Decimal/date industry fields must save into the JSON attributes for every business type."""
    company = jeweller["company"]
    unit = Unit.objects.for_company(company).first() or Unit.objects.create(company=company, name="pcs")
    sample = {"weight_grams": "12.5", "making_charge": "10", "mileage": "1200", "stone_value": "50",
              "minimum_order_quantity": "2.5", "warranty_months": "12", "model_year": "2025",
              "production_lead_days": "3", "preparation_minutes": "5", "lead_time_days": "7",
              "service_interval_days": "90", "production_date": "2026-01-01", "expiry_date": "2026-12-31",
              "purity": "22K", "making_mode": "fixed", "serial_required": "", "assembly_required": "on"}
    for n, code in enumerate(BusinessProductForm.INDUSTRY_FIELDS):
        business_type = BusinessType.objects.filter(code=code).first()
        if business_type is None:
            continue
        company.business_type = business_type
        data = {"sku": f"SKU{n}", "name": f"Item {code}", "unit": unit.id, "cost_price": "1",
                "selling_price": "2", "reorder_level": "0", "wholesale_price": "1.5", "carton_quantity": "6"}
        for name in BusinessProductForm.INDUSTRY_FIELDS[code]:
            data[name] = sample.get(name, "text")
        form = BusinessProductForm(data=data, company=company)
        assert form.is_valid(), (code, form.errors)
        product = form.save(commit=False)
        product.company = company
        product.save()
        product.refresh_from_db()
        assert product.attributes["wholesale_price"] == "1.5", code
