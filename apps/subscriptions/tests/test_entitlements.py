import pytest
from django.core.exceptions import ValidationError
from apps.modules.models import Module
from apps.subscriptions.services import entitlement_snapshot, require_module, enforce_limit

pytestmark = pytest.mark.django_db


def test_plan_module_entitlement_is_server_side(tenant_a):
    module = Module.objects.create(code="crm-test", name="CRM Test")
    tenant_a.subscription.plan.modules.add(module)
    assert "crm-test" in entitlement_snapshot(tenant_a)["modules"]
    require_module(tenant_a, "crm-test")
    with pytest.raises(ValidationError):
        require_module(tenant_a, "not-in-plan")


def test_user_limit_enforced_without_deleting_data(tenant_a):
    tenant_a.subscription.plan.max_users = 1
    tenant_a.subscription.plan.save(update_fields=["max_users"])
    with pytest.raises(ValidationError):
        enforce_limit(tenant_a, "users")
