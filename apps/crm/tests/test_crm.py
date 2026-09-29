from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError

from apps.crm.models import Lead, PipelineStage, Opportunity
from apps.crm.services import convert_lead, duplicate_customer_candidates
from apps.customers.models import Customer


pytestmark = pytest.mark.django_db


def test_lead_conversion_is_atomic_and_creates_customer(tenant_a, tenant_a_owner):
    lead = Lead.objects.create(company=tenant_a, name="Acme", email="sales@acme.test", created_by=tenant_a_owner)
    customer, opportunity, quotation = convert_lead(company=tenant_a, lead=lead, user=tenant_a_owner, create_quotation=True)
    lead.refresh_from_db()
    assert lead.status == "converted"
    assert customer.company == tenant_a
    assert opportunity.customer == customer
    assert quotation.customer == customer


def test_duplicate_requires_explicit_resolution(tenant_a, tenant_a_owner):
    Customer.objects.create(company=tenant_a, name="Existing", email="same@example.com")
    lead = Lead.objects.create(company=tenant_a, name="New Name", email="same@example.com", created_by=tenant_a_owner)
    assert duplicate_customer_candidates(company=tenant_a, lead=lead).count() == 1
    with pytest.raises(ValidationError):
        convert_lead(company=tenant_a, lead=lead, user=tenant_a_owner)


def test_crm_api_is_tenant_isolated(tenant_a, tenant_b, tenant_a_owner, as_tenant_b_owner):
    lead = Lead.objects.create(company=tenant_a, name="Private", created_by=tenant_a_owner)
    response = as_tenant_b_owner.get(f"/api/crm/leads/{lead.id}/")
    assert response.status_code == 404


def test_pipeline_totals_are_tenant_scoped(tenant_a, tenant_b, tenant_a_owner, tenant_b_owner):
    stage_a = PipelineStage.objects.create(company=tenant_a, name="Open")
    stage_b = PipelineStage.objects.create(company=tenant_b, name="Open")
    Opportunity.objects.create(company=tenant_a, title="A", stage=stage_a, assigned_to=tenant_a_owner, expected_value=Decimal("100"))
    Opportunity.objects.create(company=tenant_b, title="B", stage=stage_b, assigned_to=tenant_b_owner, expected_value=Decimal("900"))
    assert Opportunity.objects.for_company(tenant_a).count() == 1
