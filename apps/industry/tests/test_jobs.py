"""Service job cards: new job (walk-in and appointment), parts and labour, status, bill, technician
phone page, customer status page, calendar and online booking → job."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.employees.models import Employee
from apps.industry import jobs
from apps.inventory.models import Product, Unit
from apps.inventory.services import record_stock_movement
from apps.tenants.models import Company
from apps.verticals.saloon.models import ServiceCase

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _garage(email, kind="auto_garage"):
    client = Client(REMOTE_ADDR=f"10.7.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Garage {email}", "business_type": kind, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    staff = Employee.objects.create(company=company, name="Rafeeq", phone="+974 5555 3333")
    return company, client, staff


def _new_job(client, staff, **extra):
    data = {"new_name": "Ameen", "new_phone": "+974 5555 1234", "subject_name": "Toyota Camry", "identifier": "123456",
            "title": "Oil change + brake check", "staff": staff.id, "duration": 60, "priority": "normal", **extra}
    return client.post(reverse("webapp:service_case_add"), data)


def test_walk_in_job_parts_labour_bill():
    company, owner, staff = _garage("j1@t.qa")
    r = _new_job(owner, staff)
    job = ServiceCase.objects.get(company=company)
    assert r.status_code == 302 and job.number.startswith("JOB-") and job.profile.identifier == "123456"
    unit = Unit.objects.create(company=company, name="pcs")
    oil = Product.objects.create(company=company, sku="OIL-5W30", name="Engine oil 5W-30", unit=unit, selling_price=Decimal("45"))
    from apps.inventory.models import Warehouse
    wh = Warehouse.objects.for_company(company).filter(is_active=True).first() or Warehouse.objects.create(company=company, name="Main", is_default=True)
    record_stock_movement(company=company, product=oil, warehouse=wh, quantity=Decimal("10"), reason="adjustment", reference="open")
    act = reverse("webapp:job_action", args=[job.id])
    owner.post(act, {"do": "line", "product_id": oil.id, "quantity": "4"})
    owner.post(act, {"do": "line", "description": "Labour 1 hour", "quantity": "1", "unit_price": "60"})
    assert jobs.total(job) == Decimal("240")
    page = owner.get(reverse("webapp:service_case_detail", args=[job.id])).content.decode()
    assert "Engine oil 5W-30" in page and "Labour 1 hour" in page and "240.00" in page and "wa.me/97455551234" in page

    owner.post(act, {"do": "status", "status": "in_progress"})
    owner.post(act, {"do": "status", "status": "ready"})
    job.refresh_from_db()
    assert job.status == "ready" and job.started_at and job.finished_at
    owner.post(act, {"do": "bill", "method": "cash", "discount": "10"})
    job.refresh_from_db()
    assert job.status == "completed" and job.invoice and job.invoice.total == Decimal("230")
    assert oil.current_stock(wh) == Decimal("6")
    owner.post(act, {"do": "line", "description": "Late add", "unit_price": "5"})  # closed: refused
    assert job.lines.count() == 2
    assert "JOB-" in owner.get(reverse("webapp:job_print", args=[job.id])).content.decode()
    _new_job(owner, staff, new_name="Basil", new_phone="+974 5555 2222", subject_name="Nissan Sunny", identifier="7788")
    _new_job(owner, staff, new_name="Cyril", new_phone="", subject_name="", identifier="")  # 3rd customer, blank record no.
    assert ServiceCase.objects.filter(company=company).count() == 3


def test_appointment_clash_calendar_and_phone_pages():
    company, owner, staff = _garage("j2@t.qa")
    at = (timezone.localtime() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    _new_job(owner, staff, scheduled_at=at.strftime("%Y-%m-%dT%H:%M"))
    r = _new_job(owner, staff, scheduled_at=(at + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"), title="AC gas refill")
    assert r.status_code == 200 and "already has" in r.content.decode()  # warned first
    _new_job(owner, staff, scheduled_at=(at + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"), title="AC gas refill",
             confirm_clash="1")
    assert ServiceCase.objects.filter(company=company).count() == 2
    cal = owner.get(reverse("webapp:job_calendar"), {"day": at.date().isoformat()}).content.decode()
    assert "Oil change" in cal and "AC gas refill" in cal and "Rafeeq" in cal

    owner.post(reverse("webapp:technician_link_action", args=[staff.id]), {"do": "make"})
    link = staff.technician_link
    tech = Client()
    url = reverse("webapp:technician_page", args=[link.token])
    html = tech.get(url).content.decode()
    assert "Oil change" in html and "Toyota Camry" in html and "Labour" not in html  # no prices on the phone page
    job = ServiceCase.objects.get(company=company, title__startswith="Oil")
    tech.post(url, {"job_id": job.id, "do": "in_progress"})
    tech.post(url, {"job_id": job.id, "do": "note", "notes": "Brake pads worn — need new set"})
    job.refresh_from_db()
    assert job.status == "in_progress" and job.case_notes.filter(notes__contains="Brake pads").exists()

    status = Client().get(reverse("webapp:job_status_page", args=[job.token])).content.decode()
    assert job.number in status and "In progress" in status
    other_company, other_owner, other_staff = _garage("j3@t.qa")
    other_link = jobs.technician_link(other_staff)
    assert Client().post(reverse("webapp:technician_page", args=[other_link.token]),
                         {"job_id": job.id, "do": "ready"}).status_code == 404  # not their job
    assert other_owner.get(reverse("webapp:service_case_detail", args=[job.id])).status_code == 404
    owner.post(reverse("webapp:technician_link_action", args=[staff.id]), {"do": "off"})
    assert Client().get(url).status_code == 404


def test_online_appointment_becomes_a_job():
    from apps.industry.models import OnlineBooking
    company, owner, staff = _garage("j4@t.qa", kind="dental_clinic")
    day = timezone.localdate() + timedelta(days=2)
    req = OnlineBooking.objects.create(company=company, number="OB-1", kind="appointment", name="Sara", phone="+974 5555 9999",
                                       item_name="Teeth cleaning", date=day, time=timezone.datetime(2000, 1, 1, 11, 30).time())
    r = owner.post(reverse("webapp:ob_detail", args=[req.id]), {"action": "confirm"})
    job = ServiceCase.objects.get(company=company)
    assert r.status_code == 302 and r.url == reverse("webapp:service_case_detail", args=[job.id])
    assert job.title == "Teeth cleaning" and timezone.localtime(job.scheduled_at).hour == 11
    req.refresh_from_db()
    assert req.linked == f"job:{job.id}" and req.status == "confirmed"
