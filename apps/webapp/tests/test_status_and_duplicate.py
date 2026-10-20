"""One click: a repair's status from the list or by dragging it on the board, and a quotation / job order
duplicated with one button."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.customers.models import Customer
from apps.inventory.models import Product, Unit
from apps.sales import services as sales
from apps.sales.models import Quotation

from .test_overview_panels import _business

pytestmark = pytest.mark.django_db


def test_repair_status_list_and_board():
    from apps.verticals.mobile_shop.models import MobileRepairJob
    company, _user, c = _business("mobile_shop")
    c.post(reverse("webapp:mobile_repair_add"), {
        "new_customer_name": "Faisal", "new_customer_phone": "5555 1234", "device_description": "iPhone 13",
        "imei": "356789012345678", "reported_issue": "Cracked screen", "lock_code": "1234",
        "accessory_list": ["Charger"], "estimated_cost": "300", "advance": "0", "promised_date": "2030-01-05",
        "status": "received"})
    job = MobileRepairJob.objects.get(company=company)
    url = reverse("webapp:mobile_repair_status", args=[job.id])
    assert url in c.get(reverse("webapp:mobile_repair_list")).content.decode()
    board = c.get(reverse("webapp:mobile_repair_list") + "?view=board").content.decode()
    assert "kb-board" in board and "iPhone 13" in board and "js/kanban.js" in board

    r = c.post(url, {"status": "diagnosing"}, HTTP_X_REQUESTED_WITH="fetch")
    assert r.json()["ok"] and r.json()["status"] == "diagnosing"
    c.post(url, {"status": "ready", "next": reverse("webapp:mobile_repair_list")})
    job.refresh_from_db()
    assert job.status == "ready"
    # finishing bills the repair, so it is never a one-click step
    assert c.post(url, {"status": "completed"}, HTTP_X_REQUESTED_WITH="fetch").status_code == 400
    job.refresh_from_db()
    assert job.status == "ready"


def test_duplicate_quotation_and_job_order():
    company, user, c = _business("recruitment_agency")
    customer = Customer.objects.create(company=company, name="Al Noor")
    unit = Unit.objects.create(company=company, name="pcs")
    product = Product.objects.create(company=company, sku="SV1", name="Placement fee", unit=unit)
    q = sales.create_quotation(company=company, user=user, customer=customer, date=date(2026, 1, 5), notes="Net 30",
                               lines=[{"product": product, "quantity": Decimal("3"), "unit_price": Decimal("1500")}])
    r = c.post(reverse("webapp:quotation_detail", args=[q.id]), {"action": "duplicate"})
    copy = Quotation.objects.for_company(company).exclude(id=q.id).get()
    assert r.url == reverse("webapp:quotation_detail", args=[copy.id])
    assert copy.status == "draft" and copy.notes == "Net 30" and copy.number != q.number
    assert [(l.product_id, l.quantity, l.unit_price) for l in copy.lines.all()] == [(product.id, Decimal("3.000"), Decimal("1500.00"))]

    from apps.industry import recruitment as svc
    from apps.industry.models import JobOrder
    job = svc.create_job_order(company=company, user=user, client=customer, position="Electrician", vacancies=4,
                               salary=Decimal("2200"), skills="MEP")
    job.publish_online = True
    job.status = "closed"
    job.save()
    c.post(reverse("webapp:rec_job_detail", args=[job.id]), {"action": "duplicate"})
    dup = JobOrder.objects.for_company(company).exclude(id=job.id).get()
    assert (dup.position, dup.vacancies, dup.salary, dup.skills) == ("Electrician", 4, Decimal("2200.00"), "MEP")
    assert dup.status == "open" and not dup.publish_online and dup.number != job.number
