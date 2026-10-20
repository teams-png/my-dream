"""Platform admin: delete a client permanently right now, only after typing its name; nobody else can."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.subscriptions.models import DeletedAccountLog
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _admin():
    user = get_user_model().objects.create_user(username="pa@bp.qa", email="pa@bp.qa", password="Pa-Pass-12345",
                                                is_platform_admin=True, is_superuser=True, is_staff=True)
    c = Client()
    c.force_login(user)
    return c


def test_owner_cannot_delete_their_company(tenant_a, tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    url = reverse("webapp:platform_admin_company_purge", args=[tenant_a.id])
    assert c.get(url).status_code in (302, 403)
    c.post(url, {"confirm_name": tenant_a.name})
    assert Company._base_manager.filter(pk=tenant_a.pk).exists()


def test_wrong_name_deletes_nothing_right_name_deletes_everything(tenant_a, tenant_a_owner, tenant_b):
    Customer.objects.create(company=tenant_a, name="Ravi Kumar")
    Customer.objects.create(company=tenant_b, name="Other Shop Customer")
    pa = _admin()
    detail = pa.get(reverse("webapp:platform_admin_company_detail", args=[tenant_a.id])).content.decode()
    url = reverse("webapp:platform_admin_company_purge", args=[tenant_a.id])
    assert url in detail
    page = pa.get(url).content.decode()
    assert "cannot be undone" in page and tenant_a.name in page

    page = pa.post(url, {"confirm_name": "something else"}).content.decode()
    assert "doesn&#x27;t match" in page or "doesn't match" in page
    assert Company._base_manager.filter(pk=tenant_a.pk).exists()

    r = pa.post(url, {"confirm_name": "  " + tenant_a.name.upper() + " "})
    assert r.status_code == 302 and r.url == reverse("webapp:platform_admin_company_list")
    assert not Company._base_manager.filter(pk=tenant_a.pk).exists()
    assert not Customer.objects.filter(name="Ravi Kumar").exists()
    assert not get_user_model().objects.filter(pk=tenant_a_owner.pk).exists()
    assert DeletedAccountLog.objects.filter(company_name=tenant_a.name, reason="Deleted by the platform admin").exists()
    # the other business is untouched
    assert Customer.objects.filter(company=tenant_b, name="Other Shop Customer").exists()
