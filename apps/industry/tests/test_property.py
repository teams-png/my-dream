from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry import property as svc
from apps.industry.models import Lease, Property, RentalUnit, RentCharge
from apps.sales import services as sales
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def pm(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Doha Homes", "business_type": "property_management", "country": "Qatar", "full_name": "Sam P",
        "email": "s@homes.test", "phone": "", "password": "Doha-Homes-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="s@homes.test")
    tower = Property.objects.create(company=company, name="Pearl Tower")
    a1 = RentalUnit.objects.create(company=company, property=tower, name="A-101", monthly_rent=Decimal("6500"), bedrooms=2)
    a2 = RentalUnit.objects.create(company=company, property=tower, name="A-102", monthly_rent=Decimal("5000"))
    t1 = Customer.objects.create(company=company, name="Tenant One", phone="5551")
    t2 = Customer.objects.create(company=company, name="Tenant Two", phone="5552")
    return {"company": company, "user": company.memberships.first().user, "a1": a1, "a2": a2, "t1": t1, "t2": t2,
            "client": client}


def lease(d, unit, tenant, start, end, rent="6500", **kw):
    return svc.create_lease(company=d["company"], user=d["user"], unit=d[unit], tenant=d[tenant], start_date=start,
                            end_date=end, monthly_rent=Decimal(rent), **kw)


def test_one_active_lease_per_unit(pm):
    first = lease(pm, "a1", "t1", date(2026, 1, 1), date(2026, 12, 31), bill_first_month=False)
    assert first.number.startswith("LS-")
    with pytest.raises(ValidationError):
        lease(pm, "a1", "t2", date(2026, 6, 1), date(2027, 5, 31), bill_first_month=False)
    with pytest.raises(ValidationError):
        lease(pm, "a2", "t2", date(2026, 6, 1), date(2026, 5, 1), bill_first_month=False)
    with pytest.raises(ValidationError):
        lease(pm, "a2", "t2", date(2026, 6, 1), date(2027, 5, 1), due_day=31, bill_first_month=False)
    svc.end_lease(first, on=date(2026, 5, 31), early=True)
    assert first.end_date == date(2026, 5, 31) and first.status == "terminated"
    lease(pm, "a1", "t2", date(2026, 6, 1), date(2027, 5, 31), bill_first_month=False)  # free again


def test_rent_run_bills_each_lease_once_with_due_date(pm):
    lease(pm, "a1", "t1", date(2026, 1, 1), date(2026, 12, 31), due_day=5, bill_first_month=False)
    lease(pm, "a2", "t2", date(2026, 10, 15), date(2027, 10, 14), rent="5000", bill_first_month=False)
    assert len(svc.leases_for_month(pm["company"], "2026-09")) == 1
    invoices = svc.generate_month(company=pm["company"], user=pm["user"], key="2026-10")
    assert sorted(i.total for i in invoices) == [Decimal("5000"), Decimal("6500")]
    assert svc.generate_month(company=pm["company"], user=pm["user"], key="2026-10") == []
    charge = RentCharge.objects.get(lease__unit=pm["a1"], period="2026-10")
    assert charge.due_date == date(2026, 10, 5) and charge.invoice.due_date == date(2026, 10, 5)
    assert svc.leases_for_month(pm["company"], "2027-01") == [Lease.objects.get(unit=pm["a2"])]  # a1 lease ended


def test_overdue_and_summary(pm):
    l1 = lease(pm, "a1", "t1", date(2026, 9, 1), date(2027, 8, 31), due_day=1)  # bills September
    lease(pm, "a2", "t2", date(2026, 9, 1), date(2027, 8, 31), rent="5000", due_day=1)
    inv2 = RentCharge.objects.get(lease__unit=pm["a2"]).invoice
    sales.record_customer_payment(company=pm["company"], user=pm["user"], customer=pm["t2"], amount=Decimal("5000"),
                                  date=date(2026, 9, 1), invoice=inv2)
    rows = svc.overdue(pm["company"], today=date(2026, 9, 11))
    assert [(r["charge"].lease_id, r["due"], r["days"]) for r in rows] == [(l1.pk, Decimal("6500.00"), 10)]
    s = svc.summary(pm["company"], today=date(2026, 9, 11))
    assert (s["units"], s["occupied"], s["occupancy"], s["rent_roll"]) == (2, 2, 100, Decimal("11500.00"))
    assert (s["billed"], s["collected"]) == (Decimal("11500.00"), Decimal("5000.00"))


def test_pages(pm):
    c, d = pm["client"], pm
    for name in ("property_home", "property_add", "unit_add", "lease_list", "lease_add", "rent_run"):
        assert c.get(reverse(f"webapp:{name}")).status_code == 200, name
    resp = c.post(reverse("webapp:lease_add"), {
        "unit": d["a2"].id, "new_tenant_name": "New Family", "new_tenant_phone": "5559", "start_date": "2026-09-01",
        "end_date": "2027-08-31", "monthly_rent": "5000", "due_day": "3", "security_deposit": "5000", "bill_first_month": "on"})
    assert resp.status_code == 302
    new = Lease.objects.get(tenant__name="New Family")
    assert RentCharge.objects.filter(lease=new, period="2026-09").exists()
    assert c.get(reverse("webapp:lease_detail", args=[new.id])).status_code == 200
    home = c.get(reverse("webapp:property_home"))
    assert "New Family" in home.content.decode() or "A-102" in home.content.decode()
    c.post(reverse("webapp:lease_detail", args=[new.id]), {"action": "terminate"})
    new.refresh_from_db()
    assert new.status in ("terminated", "ended")


def test_receive_rent_reminder_and_renewal(pm):
    c = pm["client"]
    first = lease(pm, "a1", "t1", date(2026, 1, 1), date(2026, 12, 31), bill_first_month=True)
    svc.bill(company=pm["company"], user=pm["user"], leases=[first], key="2026-02")
    assert "Jan 2026, Feb 2026" in svc.rent_message(first) and "13000.00" in svc.rent_message(first)
    page = c.get(reverse("webapp:lease_detail", args=[first.id])).content.decode()
    assert "Receive rent" in page and "WhatsApp rent reminder" in page
    with pytest.raises(ValidationError):
        svc.receive_rent(first, user=pm["user"], amount="20000")
    c.post(reverse("webapp:lease_detail", args=[first.id]), {"action": "receive", "amount": "9000", "method": "bank"})
    jan, feb = [ch.invoice for ch in first.charges.select_related("invoice").order_by("period")]
    jan.refresh_from_db(); feb.refresh_from_db()
    assert jan.amount_paid == Decimal("6500") and feb.amount_paid == Decimal("2500")
    svc.receive_rent(first, user=pm["user"], amount="4000", method="cash")
    assert "fully paid" in svc.rent_message(first)
    resp = c.post(reverse("webapp:lease_detail", args=[first.id]), {"action": "renew", "months": "12", "increase": "5"})
    new = Lease.objects.get(unit=pm["a1"], start_date=date(2027, 1, 1))
    assert resp.status_code == 302 and new.end_date == date(2027, 12, 31) and new.monthly_rent == Decimal("6825")
    assert new.tenant == pm["t1"] and new.number.startswith("LS-")
    with pytest.raises(ValidationError):
        svc.renew_lease(first, user=pm["user"])
    assert "Renewed as" in c.get(reverse("webapp:lease_detail", args=[first.id])).content.decode()
    assert c.get(reverse("webapp:property_home")).status_code == 200


def test_first_month_due_not_before_start(pm):
    mid = lease(pm, "a2", "t2", date(2026, 3, 20), date(2027, 3, 19), rent="5000", due_day=5)
    charge = mid.charges.get()
    assert charge.period == "2026-03" and charge.due_date == date(2026, 3, 20)
