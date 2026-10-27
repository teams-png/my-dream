"""The retail report shows size / colour only for shops that sell sizes and colours."""
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.inventory.models import Product, Unit
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _signup(code, email):
    cache.clear()
    client = Client(REMOTE_ADDR="10.12.0.9")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "India", "full_name": "Owner",
        "email": email, "phone": "+919847554224", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email), client


def test_grocery_report_has_no_size_or_colour_but_a_boutique_has():
    call_command("seed_platform")
    company, client = _signup("supermarket", "g1@t.in")
    Product.objects.for_company(company).exclude(size="", colour="").update(size="", colour="")
    page = client.get(reverse("webapp:retail_reports")).content.decode()
    assert "Top categories" in page and "Top sizes" not in page and "<th>Colour</th>" not in page
    unit = Unit.objects.create(company=company, name="pcs-x")
    Product.objects.create(company=company, sku="T-1", name="Kurti", unit=unit, selling_price=10, size="M")
    page = client.get(reverse("webapp:retail_reports")).content.decode()
    assert "Top sizes" in page and "<th>Colour</th>" in page


def test_product_list_shows_readable_details_without_internal_switches():
    from apps.webapp.templatetags.sample_data import attribute_pairs
    assert attribute_pairs({"item_type": "handset", "model_number": "SM-A155F", "ram": "6 GB", "network": ""}) == [
        ("Model number", "SM-A155F"), ("Ram", "6 GB")]
    call_command("seed_platform")
    company, client = _signup("mobile_shop", "m1@t.in")
    unit = Unit.objects.create(company=company, name="pcs-y")
    Product.objects.create(company=company, sku="CH-1", name="Fast charger", unit=unit, selling_price=10,
                           attributes={"item_type": "accessory", "warranty_months": 6})
    page = client.get(reverse("webapp:product_list")).content.decode()
    assert "Warranty months: 6" in page and "item_type" not in page
