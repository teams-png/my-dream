"""Ctrl+K search: finds the business's records (only its own, only what the member's role may open) and the
popup is on every app page."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.inventory.models import Product, Unit
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def test_search_finds_records_of_this_business_only(tenant_a, tenant_a_owner, tenant_b):
    Customer.objects.create(company=tenant_a, name="Ravi Kumar", phone="55512345")
    Customer.objects.create(company=tenant_b, name="Ravi Other")
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    Product.objects.create(company=tenant_a, sku="RV-1", name="Ravioli pack", unit=unit, selling_price=Decimal("9"))
    Supplier.objects.create(company=tenant_a, name="Raviz Traders")
    c = _client(tenant_a_owner)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "data-palette-open" in page and reverse("webapp:palette_search") in page and "js/palette" in page

    data = c.get(reverse("webapp:palette_search"), {"q": "ravi"}).json()["results"]
    titles = {r["title"] for r in data}
    assert {"Ravi Kumar", "Ravioli pack", "Raviz Traders"} <= titles and "Ravi Other" not in titles
    assert {r["group"] for r in data} >= {"Customers", "Products", "Suppliers"}
    assert c.get(reverse("webapp:palette_search"), {"q": "55512"}).json()["results"][0]["title"] == "Ravi Kumar"
    assert c.get(reverse("webapp:palette_search"), {"q": "r"}).json()["results"] == []  # 2 letters at least


def test_search_hides_records_the_role_cannot_open(tenant_a, user_factory):
    from apps.tenants.models import Role
    from apps.tenants.services import invite_member
    Customer.objects.create(company=tenant_a, name="Ravi Kumar")
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    Product.objects.create(company=tenant_a, sku="RV-1", name="Ravioli pack", unit=unit)
    staff = user_factory()
    invite_member(company=tenant_a, user=staff, role=Role.objects.get(company=tenant_a, name="Staff"))
    groups = {r["group"] for r in _client(staff).get(reverse("webapp:palette_search"), {"q": "ravi"}).json()["results"]}
    assert "Customers" in groups and "Products" not in groups  # Staff can't edit products
