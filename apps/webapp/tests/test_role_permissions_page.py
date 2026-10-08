"""The role permissions page only lists what applies to the business type (no restaurant rights for a spa)."""
import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.models import Role
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


def _setup(code):
    call_command("seed_platform")
    user = User.objects.create_user(username=f"o@{code}.test", email=f"o@{code}.test", password="Pass-2026-xyz!")
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=code, slug=code.replace("_", "-"), business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    role = Role.objects.create(company=company, name="Reception", is_system_role=False)
    c = Client()
    c.force_login(user)
    return role, c


def test_spa_has_no_restaurant_permissions():
    role, c = _setup("spa")
    url = reverse("webapp:role_permissions_edit", args=[role.id])
    page = c.get(url).content.decode()
    assert "Sales &amp; billing" in page and "restaurant.manage" not in page
    c.post(url, {"permissions": ["sales.create_invoice", "restaurant.manage"]})
    assert set(role.permissions.values_list("permission__code", flat=True)) == {"sales.create_invoice"}


def test_restaurant_keeps_restaurant_permissions():
    role, c = _setup("restaurant")
    page = c.get(reverse("webapp:role_permissions_edit", args=[role.id])).content.decode()
    assert "restaurant.manage" in page
