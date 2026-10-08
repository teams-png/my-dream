"""Each business type downloads its own import template (Excel or CSV) and uploads it back."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.inventory.models import Product
from apps.modules.catalog import BUSINESS_TYPE_MAP
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, provision_company_basics
from apps.webapp import product_import, xlsx

pytestmark = pytest.mark.django_db


def _owner(code, n=0):
    user = User.objects.create_user(username=f"i{n}@imp.test", email=f"i{n}@imp.test", password="Imp-Pass-2026!")
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=f"Imp {code}", slug=f"imp-{n}", business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    c = Client()
    c.force_login(user)
    return company, c


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def test_template_columns_follow_the_business():
    for n, (code, has, hasnt) in enumerate([
        ("clothing_store", ["Size", "Colour", "Variant of (SKU)", "Gender"], ["Service (yes/no)"]),
        ("medical_shop", ["Opening Stock"], ["Size"]),
        ("electronics_store", ["Warranty months", "Model number"], ["Gender"]),
        ("saloon", ["Service (yes/no)", "Gender"], ["Size"]),
        ("supermarket", ["Sold by weight (yes/no)", "Expiry date"], ["Gender"]),
    ]):
        company, _ = _owner(code, n)
        cols = product_import.columns(company)
        assert set(has) <= set(cols) and not set(hasnt) & set(cols), (code, cols)


def test_every_type_has_example_rows():
    for n, code in enumerate(sorted(BUSINESS_TYPE_MAP)):
        company, _ = _owner(code, n)
        rows = product_import.example_rows(company)
        assert rows and all(len(r) == len(product_import.columns(company)) for r in rows), code


def test_download_excel_and_upload_it_back():
    company, c = _owner("clothing_store")
    r = c.get(reverse("webapp:product_import_template"))
    assert r["Content-Type"].startswith("application/vnd.openxmlformats")
    grid = xlsx.read_rows(r.content)
    assert grid[0][:2] == ["SKU", "Name"] and len(grid) > 3
    upload = SimpleUploadedFile("mine.xlsx", r.content)
    r = c.post(reverse("webapp:product_import_csv"), {"csv_file": upload})
    assert r.status_code == 302
    shirt = Product.objects.get(company=company, sku="ITEM-003")
    variant = Product.objects.get(company=company, sku="ITEM-004")
    assert variant.parent == shirt and variant.size == "S" and variant.colour == "White"
    assert variant.attributes["gender"] == "Men" and variant.current_stock() == 4
    assert shirt.current_stock() == 0


def test_csv_services_weights_and_errors():
    company, c = _owner("supermarket")
    csv_text = ("SKU,Name,Category,Unit,Selling Price,Opening Stock,Sold by weight (yes/no),Expiry date\n"
                "T1,Tomato,Vegetables,kg,4.50,20,yes,2026-12-01\n"
                ",No sku,,pcs,1,,,\n"
                "T2,Bad price,,pcs,abc,,,\n")
    r = c.post(reverse("webapp:product_import_csv"),
               {"csv_file": SimpleUploadedFile("list.csv", csv_text.encode("utf-8-sig"))}, follow=True)
    tomato = Product.objects.get(company=company, sku="T1")
    assert tomato.attributes["sold_by_weight"] is True and tomato.attributes["expiry_date"] == "2026-12-01"
    assert tomato.current_stock() == 20
    assert "2 row(s) skipped" in r.content.decode()
    # same SKU again updates, and does not add stock twice
    c.post(reverse("webapp:product_import_csv"), {"csv_file": SimpleUploadedFile("list.csv", csv_text.encode())})
    tomato.refresh_from_db()
    assert tomato.current_stock() == 20

    company2, c2 = _owner("saloon", 9)
    text = "SKU,Name,Selling Price,Service (yes/no)\nS1,Haircut,30,yes\n"
    c2.post(reverse("webapp:product_import_csv"), {"csv_file": SimpleUploadedFile("s.csv", text.encode())})
    assert Product.objects.get(company=company2, sku="S1").is_stock_tracked is False
