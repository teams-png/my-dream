"""
Shared fixtures for the whole test suite.

Naming convention: `tenant_a` / `tenant_b` are two fully independent
companies (own Owner, own roles, own chart of accounts, own trial
subscription) — every cross-tenant test in the suite is written against
this exact pair, per the master brief's own words (Section 38):
"USER A from TENANT A must NEVER access TENANT B data."
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.subscriptions.models import SubscriptionPlan
from apps.tenants.models import Role
from apps.tenants.services import create_company_with_owner, invite_member


@pytest.fixture
def business_type(db):
    return BusinessType.objects.create(code="general_retail", name="General Retail")


@pytest.fixture
def starter_plan(db):
    """max_users=2 deliberately low, so the limit is easy to hit in tests."""
    return SubscriptionPlan.objects.create(
        name="Starter", price=Decimal("0"), billing_period="yearly", max_users=2
    )


@pytest.fixture
def user_factory(db):
    counter = {"n": 0}

    def _make(email=None, password="Sandbox-Pass-123"):
        counter["n"] += 1
        email = email or f"user{counter['n']}@example.com"
        return User.objects.create_user(username=email, email=email, password=password)

    return _make


@pytest.fixture
def company_factory(db, business_type, starter_plan, user_factory):
    def _make(name, slug, owner=None):
        owner = owner or user_factory()
        company = create_company_with_owner(
            user=owner, name=name, slug=slug, business_type=business_type
        )
        return company

    return _make


@pytest.fixture
def tenant_a(company_factory):
    return company_factory("ABC Textile", "abc-textile")


@pytest.fixture
def tenant_b(company_factory):
    return company_factory("Power Gym", "power-gym")


def _owner_of(company):
    return company.memberships.select_related("user").get(role__name="Owner").user


@pytest.fixture
def tenant_a_owner(tenant_a):
    return _owner_of(tenant_a)


@pytest.fixture
def tenant_b_owner(tenant_b):
    return _owner_of(tenant_b)


def jwt_client(user):
    """Authenticated APIClient. The company is auto-resolved by
    ActiveCompanyMiddleware from the user's (single, in these fixtures)
    active membership — see apps/tenants/middleware.py."""
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def as_tenant_a_owner(tenant_a_owner):
    return jwt_client(tenant_a_owner)


@pytest.fixture
def as_tenant_b_owner(tenant_b_owner):
    return jwt_client(tenant_b_owner)


@pytest.fixture
def member_factory(user_factory):
    """Create a user + non-owner membership in a given company under a given system role name."""

    def _make(company, role_name, email=None):
        user = user_factory(email=email)
        role = Role.objects.get(company=company, name=role_name)
        invite_member(company=company, user=user, role=role)
        return user

    return _make


@pytest.fixture
def sales_fixtures_factory(db):
    """
    Direct-ORM setup of a Unit + Warehouse + Product + Customer for a given
    company, so sales/accounting tests don't have to go through the full
    CRUD API just to get test data in place.
    """
    from apps.inventory.models import Unit, Warehouse, Product
    from apps.customers.models import Customer

    def _make(company, sku="SKU-1", stock_price=Decimal("100.00")):
        unit = Unit.objects.create(company=company, name="pcs")
        warehouse = Warehouse.objects.create(company=company, name="Main", is_default=True)
        product = Product.objects.create(
            company=company, sku=sku, name=f"Product {sku}", unit=unit,
            cost_price=stock_price / 2, selling_price=stock_price,
        )
        customer = Customer.objects.create(company=company, name="Walk-in Customer")
        return {"unit": unit, "warehouse": warehouse, "product": product, "customer": customer}

    return _make
