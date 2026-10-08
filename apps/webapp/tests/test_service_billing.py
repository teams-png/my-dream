"""Salons, spas and other service businesses get a Billing screen: services first, and who did the work."""
import json
import uuid

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.employees.models import Employee
from apps.industry import sample_kit
from apps.modules.catalog import billing_mode
from apps.modules.models import BusinessType
from apps.sales.models import SalesInvoice
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


@pytest.fixture
def salon():
    call_command("seed_platform")
    user = User.objects.create_user(username="o@salon.test", email="o@salon.test", password="Salon-Pass-2026!")
    business_type, _ = BusinessType.objects.get_or_create(code="saloon", defaults={"name": "Saloon"})
    company = create_company_with_owner(user=user, name="Style Cuts", slug="style-cuts", business_type=business_type,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    sample_kit.install(company, user)
    c = Client()
    c.force_login(user)
    return company, c


def test_which_types_bill_services():
    assert billing_mode("saloon") and billing_mode("barber_shop") and billing_mode("spa") and billing_mode("dental_clinic")
    assert not billing_mode("supermarket") and not billing_mode("restaurant") and not billing_mode("web_development")


def test_billing_screen_and_staff_on_the_bill(salon):
    company, c = salon
    page = c.get(reverse("webapp:pos")).content.decode()
    assert "Billing" in page and "Done by (staff)" in page and "Tap a service to start a bill." in page
    bar = page.split('class="rp-shortcuts"', 1)[1].split("</nav>", 1)[0]
    for url in ("webapp:dashboard", "webapp:saloon_appointment_list", "webapp:saloon_service_list"):
        assert f'href="{reverse(url)}"' in bar
    data = json.loads(page.split('id="posData"', 1)[1].split(">", 1)[1].split("</script>", 1)[0])
    names = [p["name"] for p in data["products"]]
    assert "Haircut" in names and "Saloon Service — Haircut" not in names
    stocked = [p["tracked"] for p in data["products"]]
    assert stocked == sorted(stocked)  # services (not stocked) come first
    from apps.verticals.saloon.models import SaloonService
    staff = Employee.objects.filter(company=company).first()
    haircut = SaloonService.objects.get(company=company, name="Haircut")
    body = {"client_id": str(uuid.uuid4()), "payment_method": "cash", "staff_id": staff.id,
            "lines": [{"product_id": haircut.product_id, "quantity": 1, "unit_price": "30.00"}]}
    r = c.post(reverse("webapp:pos_checkout"), json.dumps(body), content_type="application/json")
    assert r.status_code == 200, r.content
    invoice = SalesInvoice.objects.get(id=r.json()["invoice_id"])
    assert invoice.served_by == staff
    report = c.get(reverse("webapp:saloon_reports")).content.decode()
    assert "Billing by staff" in report and staff.name in report

    body.update(client_id=str(uuid.uuid4()), staff_id=999999)
    r = c.post(reverse("webapp:pos_checkout"), json.dumps(body), content_type="application/json")
    assert r.status_code == 400 and "Staff" in r.json()["error"]


def test_nav_says_billing_for_salons_and_pos_for_shops(salon):
    company, c = salon
    assert ">Billing<" in c.get(reverse("webapp:dashboard")).content.decode().replace("<span>", ">").replace("</span>", "<")


def test_new_bill_is_easy_to_find(salon):
    company, c = salon
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert page.count(f'href="{reverse("webapp:pos")}"') >= 3  # sidebar button, quick action, sales menu
    assert reverse("webapp:saloon_appointment_book") in page and "Book appointment" in page


def test_overview_shows_todays_appointments_first(salon):
    import datetime
    from django.utils import timezone
    from apps.customers.models import Customer
    from apps.verticals.saloon.models import Appointment, SaloonService
    company, c = salon
    haircut = SaloonService.objects.get(company=company, name="Haircut")
    when = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0)
    appt = Appointment.objects.create(company=company, customer=Customer.objects.filter(company=company).first(),
                                      service=haircut, stylist=Employee.objects.filter(company=company).first(),
                                      scheduled_at=when, price=haircut.product.selling_price)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Today&#x27;s appointments" in page and "Staff today" in page and "Getting started" in page
    assert page.index("Today&#x27;s appointments") < page.index("Getting started")
    assert "Business overview" not in page  # the old count tiles are gone for salons
    done = reverse("webapp:saloon_appointment_complete", args=[appt.id]) + "?next=overview"
    assert done in page
    assert c.get(done).url == reverse("webapp:dashboard")
    appt.refresh_from_db()
    assert appt.status == "completed"
