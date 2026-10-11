"""Perfume shops sell decants by the ml, wrap gifts and see sales by fragrance family / concentration / size."""
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.webapp.tests.test_expiry_shops import _shop

pytestmark = pytest.mark.django_db


def test_perfume_decants_gift_wrap_pictures_and_reports():
    from apps.customers.models import Customer
    from apps.industry import sample_kit
    from apps.inventory.models import Product, Warehouse
    from apps.inventory.pictures import pick
    from apps.sales.services import create_invoice
    company, user, c = _shop("perfume_shop")
    with override_settings(SAMPLE_DATA_KIT=True):
        sample_kit.install(company, user)
    decant = Product.objects.get(company=company, name="Oud oil decant (per ml)")
    assert decant.attributes["sold_by_ml"] and decant.unit.name == "ml"
    assert Product.objects.filter(company=company, name="Gift wrapping", is_stock_tracked=False).exists()

    pos = c.get(reverse("webapp:pos")).content.decode()
    assert '"unit": "ml"' in pos and "Quantity (ml)" in pos

    assert pick("Bakhoor 50g") == "bakhoor" and pick("Attar 12ml") == "attar"
    assert pick("Oud oil decant (per ml)") == "decant" and pick("Oud Royal 100ml") == "oud"

    oud = Product.objects.get(company=company, name="Oud Royal 100ml")
    create_invoice(company=company, user=user, customer=Customer.objects.filter(company=company).first(),
                   date=timezone.localdate(), warehouse=Warehouse.objects.filter(company=company).first(),
                   lines=[{"product": decant, "quantity": Decimal("6"), "unit_price": decant.selling_price},
                          {"product": oud, "quantity": Decimal("1"), "unit_price": oud.selling_price}])
    page = c.get(reverse("webapp:retail_reports") + "?period=all").content.decode()
    assert "Fragrance family" in page and "Oud / woody" in page and "Perfume oil" in page
    assert "Bottle size (ml)" in page and "Top colours" not in page


def test_perfume_product_form_can_sell_by_the_ml():
    from apps.inventory.models import Product
    company, user, c = _shop("perfume_shop")
    page = c.get(reverse("webapp:product_add")).content.decode()
    assert 'name="sold_by_ml"' in page
