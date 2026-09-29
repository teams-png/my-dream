"""
Phase 19 (Phase 1 Section 38). Fixtures here are deliberately built on the
same service-layer functions the app uses (tenants.services.create_company_with_owner,
invite_member) rather than raw model creation — a test that bypasses the
service layer can pass while the real registration flow is broken.
"""
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, invite_member

TEST_PASSWORD = "Testpass123!"


@pytest.fixture(autouse=True)
def seed_platform_data(db):
    """
    Runs the real seed_platform management command (business types, core
    modules, a default SubscriptionPlan) before every test — same command
    used in Render/VPS deployment (Phase 20/21), so a test failure here is
    a real seeding bug, not a test-only fixture drifting from production.
    """
    call_command("seed_platform")


@pytest.fixture
def api_client():
    return APIClient()


def make_user(email, password=TEST_PASSWORD):
    return User.objects.create_user(username=email, email=email, password=password)


@pytest.fixture
def make_company(db):
    """Usage: company, owner = make_company("gym")"""
    def _make(business_type_code="general_retail", owner_email=None, company_name=None):
        owner_email = owner_email or f"owner-{business_type_code}@example.com"
        company_name = company_name or f"{business_type_code.title()} Co"
        owner = make_user(owner_email)
        business_type = BusinessType.objects.get(code=business_type_code)
        company = create_company_with_owner(
            user=owner, name=company_name,
            slug=company_name.lower().replace(" ", "-"),
            business_type=business_type,
        )
        return company, owner
    return _make


@pytest.fixture
def auth_client(api_client):
    """Usage: client = auth_client(user) -> APIClient with JWT already attached."""
    def _auth(user, password=TEST_PASSWORD):
        resp = api_client.post("/api/accounts/login/", {"username": user.username, "password": password})
        assert resp.status_code == 200, resp.data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        return api_client
    return _auth


@pytest.fixture
def with_active_company(auth_client):
    """Logs in as `user` and selects `company` as the active company (Section 3 company switcher)."""
    def _select(user, company):
        client = auth_client(user)
        resp = client.post("/api/tenants/active-company/", {"company_id": company.id})
        assert resp.status_code == 200, resp.data
        return client
    return _select
