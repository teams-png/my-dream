import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounts.models import User
from apps.tenants.models import Company, CompanyBusinessType, CompanyMembership
from apps.subscriptions.models import Subscription

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_platform")


def _data(**over):
    data = {"business_name": "Spice Garden", "business_type": "restaurant", "country": "Qatar",
            "full_name": "Anu Thomas", "email": "anu@spice.test", "phone": "55551234",
            "password": "Tasty-Food-2026!", "accept_terms": "on", "website": ""}
    data.update(over)
    return data


def test_landing_for_visitors_dashboard_for_users(client):
    page = client.get("/")
    assert page.status_code == 200 and b"Start free trial" in page.content
    user = User.objects.create_user(username="x@y.test", email="x@y.test", password="Strong-Pass-123")
    client.force_login(user)
    assert client.get("/").status_code in (200, 302)  # dashboard (or no-company page), not the website


def test_signup_creates_company_owner_and_trial(client):
    resp = client.post(reverse("webapp:signup"), _data())
    assert resp.status_code == 302 and resp.url == reverse("webapp:setup", kwargs={"step": "business"})
    user = User.objects.get(email="anu@spice.test")
    company = Company.objects.get(name="Spice Garden")
    assert company.default_currency == "QAR" and company.country == "Qatar"
    assert CompanyMembership.objects.get(user=user, company=company).role.name == "Owner"
    assert CompanyBusinessType.objects.filter(company=company, is_primary=True, business_type__code="restaurant").exists()
    assert Subscription.objects.filter(company=company, status="trial").exists()
    assert client.session["_auth_user_id"] == str(user.pk)
    # the new owner can open their restaurant straight away
    assert client.get(reverse("webapp:restaurant_dashboard")).status_code == 200


def test_signup_validation_and_spam_protection(client):
    User.objects.create_user(username="anu@spice.test", email="anu@spice.test", password="Strong-Pass-123")
    dup = client.post(reverse("webapp:signup"), _data())
    assert dup.status_code == 200 and b"already exists" in dup.content
    weak = client.post(reverse("webapp:signup"), _data(email="new@spice.test", password="12345678"))
    assert weak.status_code == 200 and not User.objects.filter(email="new@spice.test").exists()
    bot = client.post(reverse("webapp:signup"), _data(email="bot@spice.test", website="http://spam"))
    assert bot.status_code == 200 and not User.objects.filter(email="bot@spice.test").exists()


def test_signup_rate_limit_and_switch_off(client, settings):
    settings.SIGNUP_LIMIT_PER_IP_PER_HOUR = 1
    client.post(reverse("webapp:signup"), _data(email="a1@spice.test", business_name="A1"))
    client.logout()
    client.post(reverse("webapp:signup"), _data(email="a2@spice.test", business_name="A2"))
    assert not User.objects.filter(email="a2@spice.test").exists()
    settings.PUBLIC_SIGNUP_ENABLED = False
    assert client.get(reverse("webapp:signup")).status_code == 302
