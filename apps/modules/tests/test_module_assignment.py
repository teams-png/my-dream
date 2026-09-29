import pytest
from django.core.exceptions import ValidationError
from apps.modules.models import Module, CompanyModule
from apps.modules.services import set_company_modules, module_is_enabled

pytestmark = pytest.mark.django_db


def test_module_assignment_preserves_data_and_controls_access(tenant_a):
    crm = Module.objects.create(code="crm-commercial", name="CRM")
    tenant_a.subscription.plan.modules.add(crm)
    set_company_modules(company=tenant_a, module_codes=[crm.code])
    assert module_is_enabled(tenant_a, crm.code)
    set_company_modules(company=tenant_a, module_codes=[])
    assert not module_is_enabled(tenant_a, crm.code)
    assert CompanyModule.objects.get(company=tenant_a, module=crm).is_active is False


def test_plan_blocks_unentitled_module(tenant_a):
    premium = Module.objects.create(code="premium-only", name="Premium")
    another = Module.objects.create(code="included", name="Included")
    tenant_a.subscription.plan.modules.add(another)
    with pytest.raises(ValidationError):
        set_company_modules(company=tenant_a, module_codes=[premium.code])
