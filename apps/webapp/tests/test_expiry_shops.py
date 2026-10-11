"""Supplement shops and pharmacies sell from real batches: billing takes the batch that expires first."""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


def _shop(code):
    call_command("seed_platform")
    user = User.objects.create_user(username=f"o@{code}.test", email=f"o@{code}.test", password="Pass-2026-xyz!")
    bt, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=code, slug=code.replace("_", "-"), business_type=bt,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    c = Client()
    c.force_login(user)
    return company, user, c


@pytest.mark.parametrize("code", ["protein_shop", "medical_shop"])
def test_sample_batches_expiry_list_and_first_expiry_first_out(code):
    from apps.industry import sample_kit
    from apps.inventory.models import Product, ProductBatch, StockMovement
    from apps.sales.services import create_invoice
    company, user, c = _shop(code)
    with override_settings(SAMPLE_DATA_KIT=True):
        sample_kit.install(company, user)
    product = Product.objects.filter(company=company, tracking_type="batch").first()
    assert product is not None
    soon, later = ProductBatch.objects.filter(product=product).order_by("expiry_date")
    assert soon.expiry_date < later.expiry_date

    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Expiring soon" in page and soon.batch_number in page
    assert reverse("webapp:stock_batches") in page and "Batches &amp; expiry" in page

    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer
    create_invoice(company=company, user=user, customer=Customer.objects.filter(company=company).first(), date=timezone.localdate(),
                   lines=[{"product": product, "quantity": Decimal("1"), "unit_price": product.selling_price}],
                   warehouse=Warehouse.objects.filter(company=company).first())
    moved = StockMovement.objects.filter(product=product, reason="sale").first()
    assert moved.batch_id == soon.id  # the batch that expires first went out

    assert sample_kit.remove(company) <= 3  # only what the test bill used (item, its batch, customer) is kept


def test_new_protein_products_are_batch_tracked():
    company, user, c = _shop("protein_shop")
    form = c.get(reverse("webapp:product_add")).content.decode()
    assert "Flavour" in form and "Servings per pack" in form
    from apps.inventory.models import Unit
    unit = Unit.objects.create(company=company, name="tub")
    r = c.post(reverse("webapp:product_add"), {"sku": "WHEY-5", "name": "Whey 5 lb", "unit": unit.id, "cost_price": "150",
                                               "selling_price": "250", "reorder_level": "2", "is_stock_tracked": "on",
                                               "flavour": "Vanilla"})
    assert r.status_code == 302, r.content.decode()[:3000]
    from apps.inventory.models import Product
    p = Product.objects.get(company=company, sku="WHEY-5")
    assert p.tracking_type == "batch" and p.attributes.get("flavour") == "Vanilla"
