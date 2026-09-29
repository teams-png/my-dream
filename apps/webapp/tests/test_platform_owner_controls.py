import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.modules.models import BusinessType
from apps.tenants.models import Company, Permission, Role, RolePermission


@pytest.mark.django_db
def test_platform_owner_controls_and_tenant_isolation(client):
    user_model = get_user_model()
    admin = user_model.objects.create_user(username="admin-control", email="admin-control@example.com", password="x", is_platform_admin=True)
    tenant = user_model.objects.create_user(username="tenant-control", email="tenant-control@example.com", password="x")
    business = BusinessType.objects.create(code="control_test", name="Control Test")
    company = Company.objects.create(name="Controlled", slug="controlled-test", business_type=business)
    other = Company.objects.create(name="Other", slug="other-test", business_type=business)
    role = Role.objects.create(company=company, name="Staff")
    permission = Permission.objects.create(code="control.view", label="View control", module="control")
    url = reverse("webapp:platform_admin_role_permissions", args=[company.pk, role.pk])

    client.force_login(tenant)
    assert client.post(url, {"permissions": [permission.pk]}).status_code == 302
    assert not RolePermission.objects.filter(role=role).exists()

    client.force_login(admin)
    assert client.post(url, {"permissions": [permission.pk]}).status_code == 302
    assert RolePermission.objects.filter(role=role, permission=permission).exists()
    assert client.get(reverse("webapp:platform_admin_role_permissions", args=[other.pk, role.pk])).status_code == 404
    assert client.get(reverse("webapp:platform_admin_company_restore", args=[company.pk])).status_code == 405
    company.is_active = False
    company.save(update_fields=["is_active"])
    assert client.post(reverse("webapp:platform_admin_company_restore", args=[company.pk])).status_code == 302
    company.refresh_from_db()
    assert company.is_active
