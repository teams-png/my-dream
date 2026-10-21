"""Platform admin deletes a business type permanently: no restore, never offered again (not even after a deploy),
clients already on it keep working, and an unused custom type is removed from the database."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.modules.models import BusinessType
from apps.tenants.models import CompanyBusinessType

pytestmark = pytest.mark.django_db


def _admin():
    user = get_user_model().objects.create_user(username="pa@bp.qa", email="pa@bp.qa", password="Pa-Pass-12345",
                                                is_platform_admin=True, is_superuser=True, is_staff=True)
    c = Client()
    c.force_login(user)
    return c


def test_owner_cannot_delete_a_business_type(tenant_a_owner):
    bt = BusinessType.objects.create(code="kite_shop", name="Kite Shop")
    c = Client()
    c.force_login(tenant_a_owner)
    c.post(reverse("webapp:platform_business_type_delete", args=[bt.id]))
    assert BusinessType.objects.get(pk=bt.pk).is_active


def test_unused_custom_type_is_deleted_for_good():
    bt = BusinessType.objects.create(code="kite_shop", name="Kite Shop")
    pa = _admin()
    assert reverse("webapp:platform_business_type_delete", args=[bt.id]) in pa.get(
        reverse("webapp:platform_business_type_list")).content.decode()
    assert "deleted for good" in pa.get(reverse("webapp:platform_business_type_delete", args=[bt.id])).content.decode()
    assert pa.post(reverse("webapp:platform_business_type_delete", args=[bt.id])).status_code == 302
    assert not BusinessType.objects.filter(pk=bt.pk).exists()


def test_catalogue_type_in_use_is_deleted_for_good(tenant_a, tenant_a_owner):
    from django.core.management import call_command
    bt = tenant_a.business_type
    pa = _admin()
    page = pa.get(reverse("webapp:platform_business_type_delete", args=[bt.id])).content.decode()
    assert tenant_a.name in page and "cannot be undone" in page and "restore" not in page.lower()
    pa.post(reverse("webapp:platform_business_type_delete", args=[bt.id]))
    bt.refresh_from_db()
    assert not bt.is_active
    # not offered at sign-up or to new clients any more
    signup = Client().get(reverse("webapp:signup")).content.decode()
    assert f'value="{bt.code}"' not in signup
    register = pa.get(reverse("webapp:register_client")).content.decode()
    assert f'value="{bt.code}"' not in register
    # the client already on it keeps working
    owner = Client()
    owner.force_login(tenant_a_owner)
    assert owner.get(reverse("webapp:dashboard")).status_code == 200
    # gone from the admin list, no restore, and a deploy (seed_platform) does not bring it back
    listing = pa.get(reverse("webapp:platform_business_type_list")).content.decode()
    assert f"<code>{bt.code}</code>" not in listing and "Restore" not in listing
    call_command("seed_platform")
    bt.refresh_from_db()
    assert not bt.is_active


def test_deleted_type_cannot_be_ticked_for_another_client(tenant_a, tenant_b):
    other = BusinessType.objects.create(code="kite_shop", name="Kite Shop", is_active=False)
    pa = _admin()
    url = reverse("webapp:platform_admin_manage_business_suites", args=[tenant_b.id])
    assert "Kite Shop" not in pa.get(url).content.decode()
    pa.post(url, {"business_types": [other.id]})
    assert not CompanyBusinessType.objects.filter(company=tenant_b, business_type=other, is_active=True).exists()
