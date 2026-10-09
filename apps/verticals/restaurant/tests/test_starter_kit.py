"""Kerala starter kit: a new restaurant opens with a full menu, pictures, stations, tables, sample staff and
expenses — and can remove it in one click."""
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounting.models import JournalEntry
from apps.employees.models import Employee
from apps.expenses.models import Expense
from apps.inventory.models import Product
from apps.tenants.models import Company
from apps.verticals.restaurant import kerala_menu, services, starter_kit
from apps.verticals.restaurant.models import DiningTable, KitchenStation, RestaurantMenuItem, StarterSample

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))
TOTAL = sum(len(rows) for rows in kerala_menu.DISHES.values())


def _signup(code, email, country="Qatar"):
    client = Client(REMOTE_ADDR=f"10.11.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": country, "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email), client


@pytest.fixture(autouse=True)
def platform():
    cache.clear()
    call_command("seed_platform")


@override_settings(RESTAURANT_STARTER_KIT=True)
def test_new_restaurant_opens_with_the_kerala_kit():
    company, client = _signup("restaurant", "k1@t.qa")
    dishes = RestaurantMenuItem.objects.for_company(company)
    assert dishes.count() == TOTAL >= 120
    biryani = Product.objects.for_company(company).get(sku="KL-thalassery-chicken-biryani")
    assert biryani.category.name == "Biryani & Rice" and str(biryani.selling_price) == "18.00"
    item = biryani.restaurant_menu_item
    assert item.image.name == "restaurant/kerala/photo-thalassery-chicken-biryani.webp" and "ബിരിയാണി" in item.description
    assert item.modifier_groups.filter(name="Spice level").exists()
    assert KitchenStation.objects.for_company(company).count() == 4
    assert DiningTable.objects.for_company(company).count() == 18
    assert Employee.objects.for_company(company).count() == 10
    assert Expense.objects.for_company(company).count() == 9
    page = client.get(reverse("webapp:restaurant_setup")).content.decode()
    assert "Kerala starter menu is loaded" in page and "Remove sample data" in page


@override_settings(RESTAURANT_STARTER_KIT=True)
def test_cafe_gets_the_cafe_sections_and_other_types_get_nothing():
    cafe, _ = _signup("cafe_juice_shop", "k2@t.qa")
    names = set(Product.objects.for_company(cafe).values_list("category__name", flat=True))
    assert names and names <= kerala_menu.CAFE_CATEGORIES
    shop, _ = _signup("mobile_shop", "k3@t.qa")
    assert not StarterSample.objects.for_company(shop).exists()


@override_settings(RESTAURANT_STARTER_KIT=True)
def test_prices_follow_the_currency():
    company, _ = _signup("restaurant", "k4@t.qa", country="India")
    if company.default_currency != "INR":
        pytest.skip("country does not set INR here")
    assert str(Product.objects.for_company(company).get(sku="KL-thalassery-chicken-biryani").selling_price) == "180.00"


def test_load_and_remove_from_setup_page_keeps_dishes_already_billed():
    company, client = _signup("restaurant", "k5@t.qa")
    assert not RestaurantMenuItem.objects.for_company(company).exists()  # kit is off in tests by default
    client.post(reverse("webapp:restaurant_starter_kit"), {"action": "install", "staff": "on"})
    assert RestaurantMenuItem.objects.for_company(company).count() == TOTAL
    assert Employee.objects.for_company(company).count() == 10 and not Expense.objects.for_company(company).exists()

    porotta = Product.objects.for_company(company).get(sku="KL-kerala-porotta")
    owner = company.memberships.get(role__name="Owner").user
    order = services.create_order(company=company, channel="takeaway", waiter=owner)
    services.add_order_line(company=company, order=order, product=porotta, quantity=2)

    response = client.post(reverse("webapp:restaurant_starter_kit"), {"action": "remove"})
    assert response.status_code == 302
    left = Product.objects.for_company(company).filter(sku__startswith="KL-")
    assert list(left.values_list("sku", "is_active")) == [("KL-kerala-porotta", False)]
    assert not Employee.objects.for_company(company).filter(name__endswith="(sample)").exists()
    assert not StarterSample.objects.for_company(company).exists()


def test_removing_sample_expenses_voids_their_ledger_entries():
    company, client = _signup("restaurant", "k6@t.qa")
    owner = company.memberships.get(role__name="Owner").user
    starter_kit.install(company, owner)
    entry_ids = list(Expense.objects.for_company(company).values_list("journal_entry_id", flat=True))
    assert len(entry_ids) == 9
    from apps.accounting.models import Account
    from apps.accounting.services import account_balance
    cash = Account.objects.for_company(company).get(code="1000")
    assert account_balance(cash) > 0  # opening cash covers the sample expenses
    opening = JournalEntry.objects.for_company(company).get(source_type="starter_kit")
    starter_kit.remove(company)
    opening.refresh_from_db()
    assert opening.is_void
    assert not Expense.objects.for_company(company).exists()
    assert JournalEntry.objects.filter(id__in=entry_ids, is_void=True).count() == 9


def test_barcode_labels_work_without_the_barcode_package():
    from apps.inventory.barcode_svg import code128_svg
    svg = code128_svg("KL-kerala-porotta")
    assert svg.startswith("<svg") and "KL-kerala-porotta" in svg and svg.count("<rect") > 20
    company, client = _signup("restaurant", "k7@t.qa")
    owner = company.memberships.get(role__name="Owner").user
    starter_kit.install(company, owner, staff=False, expenses=False)
    product = Product.objects.for_company(company).get(sku="KL-chaya")
    response = client.get(reverse("webapp:product_barcode", args=[product.id]))
    assert response.status_code == 200 and response["Content-Type"] in ("image/png", "image/svg+xml")
