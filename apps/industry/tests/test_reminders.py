"""Revisit and membership reminders with a ready WhatsApp message."""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.industry import reminders
from apps.industry.models import CustomerReminder
from apps.inventory.models import Product, Unit, Warehouse
from apps.modules.models import BusinessType
from apps.sales.services import create_invoice
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


def _business(code, n=0):
    call_command("seed_platform")
    user = User.objects.create_user(username=f"r{n}@rem.test", email=f"r{n}@rem.test", password="Rem-Pass-2026!")
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name="Style Cuts", slug=f"rem-{n}", business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    return company, user


def _bill(company, user, customer, days_ago):
    product = Product.objects.get_or_create(company=company, sku="CUT", defaults={
        "name": "Haircut", "unit": Unit.objects.filter(company=company).first(), "selling_price": 30,
        "is_stock_tracked": False})[0]
    create_invoice(company=company, user=user, customer=customer,
                   date=timezone.localdate() - datetime.timedelta(days=days_ago),
                   lines=[{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("30")}],
                   warehouse=Warehouse.objects.filter(company=company).first())


def test_salon_revisit_list_and_whatsapp_link():
    company, user = _business("saloon")
    old = Customer.objects.create(company=company, name="Ahmed", phone="5555 1234")
    recent = Customer.objects.create(company=company, name="Recent", phone="5555 9999")
    nophone = Customer.objects.create(company=company, name="No phone", phone="")
    _bill(company, user, old, 40)
    _bill(company, user, recent, 5)
    _bill(company, user, nophone, 40)
    rows = reminders.due(company)
    assert [r["customer"] for r in rows] == [old]
    assert rows[0]["link"].startswith("https://wa.me/97455551234?text=") and "haircut" in rows[0]["message"]
    assert "Last visit 40 days ago" == rows[0]["reason"]
    assert reminders.due(company, days=60) == []

    c = Client()
    c.force_login(user)
    page = c.get(reverse("webapp:reminders")).content.decode()
    assert "Ahmed" in page and "wa.me/97455551234" in page
    c.post(reverse("webapp:reminder_sent"), {"customer_id": old.id, "kind": "revisit"})
    assert CustomerReminder.objects.filter(customer=old).exists()
    assert reminders.due(company) == []  # not again for 14 days


def test_gym_membership_ending():
    from apps.verticals.gym.models import GymMember
    from apps.verticals.gym.services import create_membership_plan
    company, user = _business("gym", 1)
    plan = create_membership_plan(company=company, name="Monthly", duration_days=30, price=Decimal("250"))
    today = timezone.localdate()
    soon = Customer.objects.create(company=company, name="Soon", phone="+974 5555 0001")
    later = Customer.objects.create(company=company, name="Later", phone="+974 5555 0002")
    for customer, end in ((soon, today + datetime.timedelta(days=2)), (later, today + datetime.timedelta(days=20))):
        GymMember.objects.create(company=company, customer=customer, membership_plan=plan, join_date=today,
                                 membership_start=today, membership_end=end)
    rows = reminders.due(company)
    assert [(r["kind"], r["customer"]) for r in rows] == [("membership", soon)]
    assert "Monthly" in rows[0]["message"] and "ends in 2 days" in rows[0]["reason"]


def test_other_companies_and_bad_input():
    company, user = _business("saloon", 2)
    other, _ = _business("saloon", 3)
    stranger = Customer.objects.create(company=other, name="X", phone="1")
    c = Client()
    c.force_login(user)
    assert c.post(reverse("webapp:reminder_sent"), {"customer_id": stranger.id, "kind": "revisit"}).status_code == 404
    assert c.post(reverse("webapp:reminder_sent"), {"customer_id": stranger.id, "kind": "spam"}).status_code == 400
    assert c.get(reverse("webapp:reminders") + "?days=abc").status_code == 200
