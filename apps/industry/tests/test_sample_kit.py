"""Every business type opens with sample products / services / customers, and one click removes them all."""
import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.industry import sample_kit
from apps.industry.models import SampleRecord
from apps.inventory.models import Product, ProductCategory, StockMovement, Unit
from apps.modules.catalog import BUSINESS_TYPE_MAP, business_group
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def _company(code, n=0, currency="QAR"):
    user = User.objects.create_user(username=f"o{n}@kit.test", email=f"o{n}@kit.test", password="Kit-Pass-2026!")
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=f"Kit {code}", slug=f"kit-{n}", business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency=currency)
    provision_company_basics(company=company)
    return company, user


def test_every_business_type_gets_samples_and_loses_them_cleanly():
    for n, code in enumerate(sorted(BUSINESS_TYPE_MAP)):
        company, user = _company(code, n)
        Product.objects.create(company=company, sku="MINE-1", name="My own product",
                               unit=Unit.objects.filter(company=company).first())
        made = sample_kit.install(company, user)
        if business_group(code) == "restaurant":
            assert made == 0, code  # restaurants have the Kerala menu kit instead
            continue
        found = sample_kit.summary(company)
        assert found["products"] + found["services"] >= 2, (code, found)
        assert found["customers"] == 3, code
        assert sample_kit.install(company, user) == 0  # only once
        sample_kit.remove(company)
        assert list(Product.objects.filter(company=company).values_list("sku", flat=True)) == ["MINE-1"], code
        assert not SampleRecord.objects.filter(company=company).exists()
        assert not Customer.objects.filter(company=company).exists()


def test_variants_gender_and_stock():
    company, user = _company("clothing_store")
    sample_kit.install(company, user)
    shirt = Product.objects.get(company=company, name="Men's cotton shirt", parent__isnull=True)
    sizes = sorted(shirt.variants.values_list("size", "colour"))
    assert ("M", "White") in sizes and len(sizes) == 8
    variant = shirt.variants.get(size="M", colour="White")
    assert variant.variant_label == "White / M" and variant.attributes["gender"] == "Men"
    assert variant.current_stock() == 4 and shirt.current_stock() == 0
    assert ProductCategory.objects.filter(company=company, name="Kids wear").exists()


def test_prices_follow_the_currency():
    company, user = _company("saloon", currency="INR")
    sample_kit.install(company, user)
    from apps.verticals.saloon.models import SaloonService
    haircut = SaloonService.objects.get(company=company, name="Haircut")
    assert haircut.price == 300 and haircut.product.selling_price == 300  # 30 QAR -> 300 INR


def test_vertical_records():
    from apps.industry.models import BookableResource, Course, RentalUnit
    from apps.verticals.gym.models import MembershipPlan
    from apps.verticals.sports_shop.models import SportsProductDetail
    from apps.verticals.textile.models import FabricDetail
    from apps.verticals.vehicle_wash.models import WashPackage
    checks = [("gym", MembershipPlan, 3), ("vehicle_wash", WashPackage, 4), ("hotel_apartment", BookableResource, 3),
              ("tuition_center", Course, 2), ("property_management", RentalUnit, 3),
              ("sports_shop", SportsProductDetail, 15), ("textile", FabricDetail, 4)]
    for n, (code, model, count) in enumerate(checks):
        company, user = _company(code, n)
        sample_kit.install(company, user)
        assert model.objects.filter(company=company).count() == count, code
        sample_kit.remove(company)
        assert not model.objects.filter(company=company).exists(), code


def test_used_samples_are_switched_off_not_deleted():
    from apps.sales.services import create_invoice
    company, user = _company("supermarket")
    sample_kit.install(company, user)
    milk = Product.objects.get(company=company, name="Fresh milk 1L")
    customer = Customer.objects.filter(company=company).first()
    from django.utils import timezone
    create_invoice(company=company, user=user, customer=customer, date=timezone.localdate(), lines=[{"product": milk, "quantity": 1,
                                                                         "unit_price": milk.selling_price}],
                   warehouse=StockMovement.objects.filter(product=milk).first().warehouse)
    kept = sample_kit.remove(company)
    milk.refresh_from_db()
    assert kept >= 1 and milk.is_active is False
    assert not Product.objects.filter(company=company, name="Tea bags (100)").exists()


@override_settings(SAMPLE_DATA_KIT=True)
def test_signup_installs_and_owner_removes_from_the_banner(client):
    client.post(reverse("webapp:signup"), {
        "business_name": "Style Cuts", "business_type": "saloon", "country": "Qatar", "full_name": "Owner",
        "email": "o@style.test", "phone": "", "password": "Style-Cuts-2026!", "accept_terms": "on", "website": ""})
    from apps.tenants.models import Company
    company = Company.objects.get(name="Style Cuts")
    assert sample_kit.has_samples(company)
    page = client.get(reverse("webapp:dashboard")).content.decode()
    assert "sample data" in page.lower() and reverse("webapp:sample_data") in page
    client.post(reverse("webapp:sample_data"), {"action": "remove"})
    assert not sample_kit.has_samples(company)
    client.get(reverse("webapp:dashboard"))  # shows the "removed" message once
    assert "remove sample data" not in client.get(reverse("webapp:dashboard")).content.decode().lower()
    client.post(reverse("webapp:sample_data"), {"action": "install"})
    assert sample_kit.has_samples(company)


def test_staff_cannot_remove_samples(client):
    from apps.tenants.models import CompanyMembership, Role
    company, user = _company("supermarket")
    sample_kit.install(company, user)
    staff = User.objects.create_user(username="s@kit.test", email="s@kit.test", password="Kit-Pass-2026!")
    CompanyMembership.objects.create(user=staff, company=company, role=Role.objects.get(company=company, name="Staff"))
    c = Client()
    c.force_login(staff)
    assert c.post(reverse("webapp:sample_data"), {"action": "remove"}).status_code == 403
    assert sample_kit.has_samples(company)


def test_pos_bills_variants_not_their_group():
    import json
    company, user = _company("clothing_store")
    sample_kit.install(company, user)
    c = Client()
    c.force_login(user)
    page = c.get(reverse("webapp:pos")).content.decode()
    data = json.loads(page.split('id="posData"', 1)[1].split(">", 1)[1].split("</script>", 1)[0])
    names = [(p["name"], p["variant"]) for p in data["products"]]
    assert ("Men's cotton shirt", "White / M") in names and ("Men's cotton shirt", "") not in names
