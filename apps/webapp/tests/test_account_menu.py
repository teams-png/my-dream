"""Top-right account menu and changing your own password."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_account_menu_on_app_and_admin(tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    html = c.get(reverse("webapp:dashboard")).content.decode()
    assert "data-am" in html and reverse("webapp:password_change") in html and reverse("webapp:logout") in html
    assert html.count('id="amPop"') == 1
    admin = User.objects.create_user(username="pa@bp.qa", email="pa@bp.qa", password="Pa-Pass-12345", is_platform_admin=True)
    a = Client()
    a.force_login(admin)
    html = a.get(reverse("webapp:platform_admin_dashboard")).content.decode()
    assert "data-am" in html and reverse("webapp:password_change") in html
    assert a.get(reverse("webapp:password_change")).status_code == 200


def test_change_password(tenant_a_owner):
    tenant_a_owner.set_password("Old-Pass-12345")
    tenant_a_owner.save()
    c = Client()
    c.force_login(tenant_a_owner)
    url = reverse("webapp:password_change")
    assert c.get(url).status_code == 200
    bad = c.post(url, {"old_password": "wrong", "new_password1": "New-Pass-67890", "new_password2": "New-Pass-67890"})
    assert bad.status_code == 200 and "errorlist" in bad.content.decode()
    mismatch = c.post(url, {"old_password": "Old-Pass-12345", "new_password1": "New-Pass-67890", "new_password2": "Other-67890"})
    assert mismatch.status_code == 200
    ok = c.post(url, {"old_password": "Old-Pass-12345", "new_password1": "New-Pass-67890", "new_password2": "New-Pass-67890"})
    assert ok.status_code == 302 and ok.url == url
    tenant_a_owner.refresh_from_db()
    assert tenant_a_owner.check_password("New-Pass-67890")
    assert c.get(reverse("webapp:dashboard")).status_code == 200  # still signed in

    anon = Client()
    assert anon.get(url).status_code == 302
