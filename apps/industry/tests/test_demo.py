"""Try-demo businesses: open without signing up, safe to share, renewed nightly after use."""
import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.industry import demo
from apps.sales.models import SalesInvoice
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def test_open_demo_without_signup(client):
    r = client.get(reverse("webapp:demo", args=["saloon"]))
    assert r.url == reverse("webapp:dashboard")
    company = Company.objects.get(is_demo=True, business_type__code="saloon")
    assert SalesInvoice.objects.filter(company=company).count() >= 6  # a week of sales to look at
    page = client.get(reverse("webapp:dashboard")).content.decode()
    assert "Live demo" in page and reverse("webapp:demo_exit") in page
    assert company.subscription.status == "active"
    owner = company.memberships.get(role__name="Owner").user
    assert not owner.has_usable_password()
    # a second visitor gets the same demo
    other = Client()
    other.get(reverse("webapp:demo", args=["saloon"]))
    assert Company.objects.filter(is_demo=True, business_type__code="saloon").count() == 1
    assert client.get(reverse("webapp:pos")).status_code == 200


def test_demo_blocks_risky_things(client):
    client.get(reverse("webapp:demo", args=["supermarket"]))
    for name in ("password_change", "staff_invite", "export_data", "security_settings"):
        r = client.get(reverse(f"webapp:{name}"))
        assert r.status_code == 302 and r.url == reverse("webapp:dashboard"), name
    r = client.post(reverse("webapp:company_settings"), {"name": "Rude name"})
    assert r.status_code == 302
    assert Company.objects.get(is_demo=True, business_type__code="supermarket").name == "FreshMart Supermarket"


def test_real_users_keep_their_session(client):
    user = User.objects.create_user(username="real@x.test", email="real@x.test", password="Real-Pass-2026!")
    client.force_login(user)
    client.get(reverse("webapp:demo", args=["saloon"]))
    assert int(client.session["_auth_user_id"]) == user.id


def test_unknown_demo_and_exit(client):
    assert client.get(reverse("webapp:demo", args=["nope"])).status_code == 404
    client.get(reverse("webapp:demo", args=["mobile_shop"]))
    r = client.get(reverse("webapp:demo_exit"))
    assert r.url == reverse("webapp:signup") and "_auth_user_id" not in client.session


def test_nightly_reset_renews_only_used_demos():
    used = demo.ensure("saloon")
    demo.mark_used(used)
    idle = demo.ensure("clothing_store")
    assert demo.nightly_reset() == 1
    used.refresh_from_db()
    assert not used.is_active and demo.current("saloon").pk != used.pk
    assert demo.current("clothing_store").pk == idle.pk


def test_demos_hidden_from_platform_client_list():
    demo.ensure("saloon")
    admin = User.objects.create_user(username="pa@x.test", email="pa@x.test", password="x", is_platform_admin=True)
    c = Client()
    c.force_login(admin)
    page = c.get(reverse("webapp:platform_admin_company_list")).content.decode()
    assert "Style Cuts Salon" not in page


def test_landing_has_demo_buttons(client):
    page = client.get(reverse("webapp:landing")).content.decode()
    assert reverse("webapp:demo", args=["restaurant"]) in page and "Try a live demo" in page
