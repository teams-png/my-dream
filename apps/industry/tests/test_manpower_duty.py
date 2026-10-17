"""Manpower stage 2: duty roster (site shifts, weekly off), office staff vs site workers, client rate vs pay
(site profit), the worker's month, the client timesheet (print / Excel) and the candidate's offer letter."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.employees import site_workers as sw
from apps.employees.models import Attendance, Employee, SiteShift, WorkSite
from apps.industry import recruitment as svc

from .test_recruitment import agency  # noqa: F401

pytestmark = pytest.mark.django_db


def _worker(c, site, name, **extra):
    data = {"name": name, "trade": "Guard", "site": site.id, "employment_status": "active", "pay_basis": "daily",
            "basic_pay": "60", "overtime_rate": "10"}
    data.update(extra)
    c.post(reverse("webapp:mp_worker_add"), data)
    return Employee.objects.get(name=name)


def test_duty_roster_profit_timesheet_and_office_split(agency):
    company, c = agency["company"], agency["client"]
    client = Customer.objects.create(company=company, name="Tower Mall")
    site = WorkSite.objects.create(company=company, name="Tower Mall – security", client=client, bill_basis="day",
                                   bill_rate=Decimal("100"), ot_bill_rate=Decimal("20"), hours_per_day=8)
    ali, ravi = _worker(c, site, "Ali"), _worker(c, site, "Ravi", pay_basis="monthly", basic_pay="2600")
    c.post(reverse("webapp:staff_add"), {"name": "Office Anu", "role_title": "Accountant", "employment_status": "active",
                                         "basic_pay": "5000"})

    # shifts: night 18:00–06:00 is 12 hours; needs 2, one assigned → 1 short
    duty = reverse("webapp:mp_duty")
    c.post(duty, {"action": "shift", "site": site.id, "name": "Night", "start": "18:00", "end": "06:00", "needed": "2"})
    night = SiteShift.objects.get(site=site)
    assert night.hours == Decimal("12")
    today = timezone.localdate()
    off_day = (today.weekday() + 1) % 7
    c.post(duty, {"action": "assign", "site": site.id, "shift": night.id, "worker": [ali.id], "weekly_off": str(off_day)})
    ali.refresh_from_db()
    assert ali.duty_shift == night and ali.site == site and ali.weekly_off == off_day
    page = c.get(duty).content.decode()
    assert "Night" in page and "1/2" in page and "1 short" in page and "Ali" in page
    assert c.get(duty + "?print=1").status_code == 200

    # site attendance: a blank hours box uses the shift's 12 hours for Ali, the site's 8 for Ravi
    d = today if today.day > 1 else today - timedelta(days=1)
    c.post(reverse("webapp:mp_attendance"), {"site": site.id, "date": d.isoformat(), f"s_{ali.id}": "present",
                                             f"ot_{ali.id}": "2", f"s_{ravi.id}": "present"})
    assert Attendance.objects.get(employee=ali, date=d).hours == Decimal("12")
    assert Attendance.objects.get(employee=ravi, date=d).hours == Decimal("8")
    assert sw.is_off(ali, today + timedelta(days=1), []) and not sw.is_off(ali, today, [])

    # profit: client pays 100/day (+20/OT hour); Ali costs 60/day + 10/OT hour
    start = sw.month_start(d)
    sites, total = sw.profit_report(company, start)
    rows = {r["employee"].name: r for r in sites[0].rows}
    assert rows["Ali"]["amount"] == Decimal("140") and rows["Ali"]["cost"] == Decimal("80") and rows["Ali"]["profit"] == Decimal("60")
    month_days = sw.working_days(company, start)
    assert rows["Ravi"]["pay"] == (Decimal("2600") / month_days).quantize(Decimal("0.01"))
    assert total["billed"] == Decimal("240") and total["ot"] == Decimal("2")
    profit = c.get(reverse("webapp:mp_profit") + f"?m={start:%Y-%m}").content.decode()
    assert "Tower Mall – security" in profit and "140.00" in profit
    assert c.get(reverse("webapp:mp_profit") + f"?m={start:%Y-%m}&format=xlsx")["Content-Type"].startswith("application/vnd.openxml")

    # the worker's own page shows the month at the site
    me = c.get(reverse("webapp:staff_detail", args=[ali.id]) + f"?m={start:%Y-%m}").content.decode()
    assert "Sites this month" in me and "Tower Mall – security" in me and "Night" in me

    # timesheet for the client to sign
    ts = c.get(reverse("webapp:mp_timesheet", args=[site.id]) + f"?m={start:%Y-%m}").content.decode()
    assert "Timesheet" in ts and "Ali" in ts and "Client signature" in ts and "+2" in ts
    assert c.get(reverse("webapp:mp_timesheet", args=[site.id]) + f"?m={start:%Y-%m}&format=xlsx").status_code == 200

    # office staff and site workers are kept apart
    staff = c.get(reverse("webapp:staff_list") + "?kind=office").content.decode()
    assert "Office Anu" in staff and "Ravi" not in staff and "Site workers (2)" in staff
    assert "Ravi" in c.get(reverse("webapp:staff_list") + "?kind=site").content.decode()
    office_att = c.get(reverse("webapp:hr_attendance")).content.decode()
    assert "Office Anu" in office_att and "Ravi" not in office_att and "Office staff only here." in office_att

    # take Ali off the shift
    c.post(duty, {"action": "unassign", "worker": [ali.id]})
    ali.refresh_from_db()
    assert ali.duty_shift is None and ali.site == site


def test_offer_letter(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    client = Customer.objects.create(company=company, name="Al Noor Contracting")
    job = svc.create_job_order(company=company, user=user, client=client, position="Electrician", vacancies=1,
                               salary=Decimal("2200"), benefits="Food, accommodation", contract_months=24,
                               work_location="Doha")
    cand = svc.create_candidate(company=company, name="Faisal", passport_no="Z123", nationality="India")
    (p,), _s = svc.submit(company=company, job=job, candidates=[cand])
    url = reverse("webapp:rec_offer_letter", args=[p.id])
    html = c.get(url).content.decode()
    assert "Offer letter" in html and "Faisal" in html and "Z123" in html and "Electrician" in html
    assert "2,200.00" in html or "2200.00" in html
    assert "Al Noor Contracting" in html and "Al Noor Contracting" not in c.get(url + "?client=0").content.decode()
    assert url in c.get(reverse("webapp:rec_placement", args=[p.id])).content.decode()
