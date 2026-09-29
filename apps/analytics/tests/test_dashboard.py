import pytest

pytestmark = pytest.mark.django_db


def test_dashboard_is_tenant_scoped(as_tenant_a_owner, tenant_a, tenant_b):
    response = as_tenant_a_owner.get("/api/analytics/dashboard/")
    assert response.status_code == 200
    assert set(("sales", "purchases", "expenses", "receivables", "payables")) <= set(response.data)


def test_dashboard_rejects_foreign_warehouse(as_tenant_a_owner, tenant_b, sales_fixtures_factory):
    warehouse = sales_fixtures_factory(tenant_b, sku="OTHER")["warehouse"]
    response = as_tenant_a_owner.get(f"/api/analytics/dashboard/?warehouse={warehouse.id}")
    assert response.status_code == 404
