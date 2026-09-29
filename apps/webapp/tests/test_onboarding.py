import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.inventory.models import Product
from apps.tenants.models import Company
from apps.verticals.restaurant.models import DiningTable, RestaurantMenuItem

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def _signup(client, business_type="supermarket", email="owner@shop.test"):
    client.post(reverse("webapp:signup"), {
        "business_name": "Corner Shop", "business_type": business_type, "country": "Qatar", "full_name": "Sam Lee",
        "email": email, "phone": "", "password": "Corner-Shop-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email)


def _url(step):
    return reverse("webapp:setup", kwargs={"step": step})


def test_new_signup_lands_in_wizard_and_dashboard_nudges(client):
    company = _signup(client)
    assert company.onboarding_completed_at is None
    assert client.get(_url("business")).status_code == 200
    assert client.get(reverse("webapp:dashboard")).context["show_setup"] is True


def test_business_step_saves_details(client):
    company = _signup(client)
    resp = client.post(_url("business"), {"name": "Corner Shop QA", "address": "Doha", "phone": "5555",
                                          "vat_number": "300000000000003", "default_currency": "QAR"})
    assert resp.status_code == 302 and resp.url == _url("catalog")
    company.refresh_from_db()
    assert company.name == "Corner Shop QA" and company.vat_number == "300000000000003"


def test_retail_catalog_creates_products_with_opening_stock(client):
    company = _signup(client)
    resp = client.post(_url("catalog"), {
        "item_name": ["Water 1.5L", "Chips", ""], "item_price": ["1.50", "3.5", ""], "item_stock": ["48", "", ""],
        "item_code": ["6291000000017", "", ""], "item_category": ["Drinks", "Snacks", ""]})
    assert resp.status_code == 302 and resp.url == _url("devices")
    water = Product.objects.get(company=company, sku="6291000000017")
    chips = Product.objects.get(company=company, name="Chips")
    assert water.current_stock() == 48 and water.category.name == "Drinks"
    assert chips.sku.startswith("P-") and chips.current_stock() == 0 and chips.is_stock_tracked


def test_bad_row_keeps_typed_values_and_saves_nothing(client):
    company = _signup(client)
    resp = client.post(_url("catalog"), {"item_name": ["Good", "Bad"], "item_price": ["2", "abc"],
                                         "item_stock": ["", ""], "item_code": ["", ""], "item_category": ["", ""]})
    assert resp.status_code == 200
    assert [r["name"] for r in resp.context["rows"]] == ["Good", "Bad"]
    assert not Product.objects.filter(company=company).exists()


def test_duplicate_code_rolls_back_whole_step(client):
    company = _signup(client)
    client.post(_url("catalog"), {"item_name": ["A"], "item_price": ["1"], "item_stock": [""], "item_code": ["X1"], "item_category": [""]})
    resp = client.post(_url("catalog"), {"item_name": ["B", "C"], "item_price": ["1", "1"], "item_stock": ["", ""],
                                         "item_code": ["", "X1"], "item_category": ["", ""]})
    assert resp.status_code == 200
    assert list(Product.objects.filter(company=company).values_list("name", flat=True)) == ["A"]


def test_restaurant_catalog_creates_menu_items_and_tables(client):
    company = _signup(client, business_type="restaurant", email="chef@food.test")
    client.post(_url("catalog"), {"item_name": ["Biryani"], "item_price": ["28"], "item_stock": [""],
                                  "item_code": [""], "item_category": ["Main course"], "tables": "6"})
    item = RestaurantMenuItem.objects.get(company=company)
    assert item.product.name == "Biryani" and not item.product.is_stock_tracked
    assert sorted(DiningTable.objects.filter(company=company).values_list("name", flat=True)) == \
        ["T1", "T2", "T3", "T4", "T5", "T6"]


def test_finishing_or_skipping_marks_setup_done(client):
    company = _signup(client)
    assert client.post(_url("devices")).url == _url("done")
    page = client.get(_url("done"))
    assert page.status_code == 200 and page.context["pos_url"] == "webapp:pos"
    company.refresh_from_db()
    assert company.onboarding_completed_at is not None
    assert client.get(reverse("webapp:dashboard")).context["show_setup"] is False

    client.logout()
    other = _signup(client, email="skip@shop.test")
    client.post(_url("business"), {"skip_all": "1"})
    other.refresh_from_db()
    assert other.onboarding_completed_at is not None


def test_staff_cannot_open_wizard(client, member_factory):
    company = _signup(client)
    client.logout()
    sub = company.subscription
    sub.plan = sub.plan.__class__.objects.filter(country=sub.plan.country, tier=sub.plan.tier, max_users=5).first()
    sub.save()
    staff = member_factory(company, "Staff")
    client.force_login(staff)
    resp = client.get(_url("business"))
    assert resp.status_code == 302 and resp.url == reverse("webapp:dashboard")
