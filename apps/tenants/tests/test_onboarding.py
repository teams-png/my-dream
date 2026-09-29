import pytest
from apps.inventory.models import Warehouse
from apps.tenants.services import complete_onboarding_step, provision_company_basics

pytestmark = pytest.mark.django_db


def test_onboarding_state_created_with_company(tenant_a):
    assert tenant_a.onboarding.accounting_setup_complete is True
    assert tenant_a.onboarding.is_complete is False


def test_provision_basics_is_idempotent(tenant_a):
    first = provision_company_basics(company=tenant_a)
    second = provision_company_basics(company=tenant_a)
    assert first.id == second.id
    assert Warehouse.objects.for_company(tenant_a).filter(name="Main Branch").count() == 1


def test_onboarding_api_is_owner_scoped(as_tenant_a_owner, tenant_a):
    response = as_tenant_a_owner.post("/api/tenants/onboarding/", {"step": "branch_setup", "complete": True}, format="json")
    assert response.status_code == 200
    assert response.data["branch_setup_complete"] is True
