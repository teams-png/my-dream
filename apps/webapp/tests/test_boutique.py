from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.template.loader import get_template
from django.urls import reverse

from apps.expenses.models import ExpenseCategory
from apps.expenses.services import record_expense
from apps.inventory.models import Product, ProductCategory, StockMovement
from apps.inventory.services import record_stock_movement
from apps.modules.models import BusinessType
from apps.sales.models import SalesInvoice, SalesInvoiceLine
from apps.webapp.forms import ExpenseForm, RegisterClientForm, VariantForm


pytestmark = pytest.mark.django_db


def test_boutique_business_type_is_seeded():
    call_command("seed_platform")
    assert BusinessType.objects.filter(
        code="ladies_fashion_boutique", name="Ladies Fashion / Boutique"
    ).exists()
    assert ("ladies_fashion_boutique", "Ladies Fashion / Boutique") in RegisterClientForm.BUSINESS_TYPES


def test_structured_variant_and_stock_are_independent(tenant_a, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a, sku="KURTI")
    red_m = Product.objects.create(
        company=tenant_a, parent=data["product"], sku="KURTI-RED-M", name="Kurti",
        unit=data["unit"], cost_price=40, selling_price=80,
        size="M", colour="Red", material="Cotton", design="Floral",
    )
    blue_l = Product.objects.create(
        company=tenant_a, parent=data["product"], sku="KURTI-BLUE-L", name="Kurti",
        unit=data["unit"], cost_price=45, selling_price=90,
        size="L", colour="Blue", material="Cotton", design="Plain",
    )
    record_stock_movement(company=tenant_a, product=red_m, warehouse=data["warehouse"], quantity=5, reason="adjustment")
    record_stock_movement(company=tenant_a, product=blue_l, warehouse=data["warehouse"], quantity=2, reason="adjustment")
    assert red_m.variant_label == "Red / M"
    assert red_m.current_stock() == Decimal("5")
    assert blue_l.current_stock() == Decimal("2")


def test_variant_form_builds_label_and_requires_size_or_colour():
    form = VariantForm({"size": "M", "colour": "Red", "material": "Cotton", "design": "Floral", "sku": "K-RED-M", "cost_price": "40", "selling_price": "80"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["variant_label"] == "Red / M"
    invalid = VariantForm({"sku": "K", "cost_price": "1", "selling_price": "2"})
    assert not invalid.is_valid()


def test_card_is_available_for_expenses_and_posts_to_bank(tenant_a, tenant_a_owner):
    assert ("card", "Card") in ExpenseForm.base_fields["payment_method"].choices
    category = ExpenseCategory.objects.create(company=tenant_a, name="Packaging")
    expense = record_expense(
        company=tenant_a, user=tenant_a_owner, category=category, date=date.today(),
        amount=Decimal("25"), description="Bags", payment_method="card",
    )
    credit_codes = set(expense.journal_entry.lines.filter(credit__gt=0).values_list("account__code", flat=True))
    assert "1010" in credit_codes


def test_retail_report_filters_and_boutique_rankings(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a, sku="ABAYA-BLK-M", stock_price=Decimal("100"))
    category = ProductCategory.objects.create(company=tenant_a, name="Abaya")
    product = data["product"]
    product.category = category
    product.size = "M"
    product.colour = "Black"
    product.cost_price = Decimal("40")
    product.save()
    invoice = SalesInvoice.objects.create(
        company=tenant_a, customer=data["customer"], invoice_number="INV-BOUTIQUE-1",
        date=date.today(), subtotal=Decimal("200"), total=Decimal("200"), tax_amount=0,
    )
    SalesInvoiceLine.objects.create(
        invoice=invoice, product=product, quantity=2, unit_price=100, line_total=200,
    )
    client.force_login(tenant_a_owner)
    response = client.get(reverse("webapp:retail_reports"), {"period": "day", "date": date.today().isoformat()})
    assert response.status_code == 200
    assert response.context["gross_profit"] == Decimal("120")
    assert response.context["top_sizes"][0]["product__size"] == "M"
    assert response.context["top_colours"][0]["product__colour"] == "Black"


def test_pos_template_contains_barcode_auto_add_logic():
    source = get_template("webapp/pos.html").template.source
    assert "confirmScan" in source
    assert "p.sku.toLowerCase() === sku" in source
    assert "addToCart(exact, scannedUnit)" in source
