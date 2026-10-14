"""Skill match for job orders, and site workers (manpower supply): IDs with expiry, site timesheet,
day / hour pay in payroll, monthly client bill per site, and a joined candidate becoming a site worker."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.employees import services as hr
from apps.employees import site_workers as sw
from apps.employees.models import Attendance, DocumentAlertLog, Employee, EmployeeDocument, SiteInvoice, WorkSite
from apps.industry import matching
from apps.industry import recruitment as svc
from apps.industry.models import Candidate, JobOrder

from .test_recruitment import agency  # noqa: F401

pytestmark = pytest.mark.django_db


def _job(company, user, **extra):
    client = Customer.objects.create(company=company, name="Al Noor Contracting")
    return svc.create_job_order(company=company, user=user, client=client, **{"position": "Electrician", "vacancies": 2, **extra})


def test_skill_match_ranks_and_explains(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    today = timezone.localdate()
    job = _job(company, user, skills="MEP, AutoCAD, Gulf licence", min_experience=Decimal("4"), max_age=40,
               salary=Decimal("2500"), gender="male")
    best = svc.create_candidate(company=company, name="Anil", trade="Electrician", skills="MEP, AutoCAD, gulf licence",
                                experience_years=Decimal("6"), gender="male", expected_salary=Decimal("2200"),
                                date_of_birth=date(today.year - 30, 1, 1), passport_expiry=today + timedelta(days=900),
                                gulf_experience=True)
    half = svc.create_candidate(company=company, name="Basil", trade="Electrician helper", skills="MEP",
                                experience_years=Decimal("2"), gender="male", passport_expiry=today + timedelta(days=30))
    wrong = svc.create_candidate(company=company, name="Chitra", trade="Electrician", skills="MEP, AutoCAD", gender="female")
    pct, reasons, blocked = matching.score(job, best)
    assert pct == 100 and not blocked and (True, "AutoCAD") in reasons
    pct2, reasons2, _b = matching.score(job, half)
    assert 0 < pct2 < 70 and (False, "AutoCAD") in reasons2
    assert matching.score(job, wrong)[2] is True  # gender is a must
    ranked = matching.rank(job, [wrong, half, best])
    assert [x.name for x in ranked] == ["Anil", "Basil", "Chitra"]

    page = c.get(reverse("webapp:rec_job_detail", args=[job.id])).content.decode()
    assert "100%" in page and "✓ AutoCAD" in page and "Anil" in page and "Chitra" not in page
    assert "Chitra" in c.get(reverse("webapp:rec_job_detail", args=[job.id]) + "?all=1").content.decode()
    detail = c.get(reverse("webapp:rec_candidate_detail", args=[best.id])).content.decode()
    assert "Best-fitting open jobs" in detail and job.number in detail
    assert c.get(reverse("webapp:rec_candidates") + "?q=autocad").content.decode().count("Anil") >= 1


def test_site_workers_ids_timesheet_pay_and_client_bill(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    today = timezone.localdate()
    for name in ("mp_home", "mp_worker_add", "mp_sites", "mp_attendance", "mp_billing"):
        assert c.get(reverse(f"webapp:{name}")).status_code == 200, name
    assert reverse("webapp:mp_home") in c.get(reverse("webapp:dashboard")).content.decode()

    c.post(reverse("webapp:mp_sites"), {"name": "Mall – cleaning", "new_client": "City Mall", "location": "Doha",
                                        "bill_basis": "hour", "bill_rate": "15", "ot_bill_rate": "20", "hours_per_day": "8"})
    site = WorkSite.objects.get(company=company)
    assert site.client.name == "City Mall" and site.is_active

    soon = today + timedelta(days=10)
    r = c.post(reverse("webapp:mp_worker_add"), {
        "name": "Ravi", "phone": "+97455550001", "trade": "Cleaner", "nationality": "India", "site": site.id,
        "employment_status": "active", "pay_basis": "hourly", "basic_pay": "6", "overtime_rate": "8",
        "id_no": "28435601234", "id_exp": soon.isoformat(), "passport_no": "P123", "passport_exp": (today - timedelta(days=1)).isoformat()})
    ravi = Employee.objects.get(company=company, name="Ravi")
    assert r.url == reverse("webapp:staff_detail", args=[ravi.id]) and ravi.worker_type == "site" and ravi.site == site
    docs = sw.documents(ravi)
    assert docs["id"].document_number == "28435601234" and docs["passport"].expiry_date < today and docs["health"] is None
    c.post(reverse("webapp:mp_worker_add"), {"name": "Sam", "trade": "Supervisor", "site": site.id, "employment_status": "active",
                                             "pay_basis": "monthly", "basic_pay": "3000", "bill_rate": "25"})
    sam = Employee.objects.get(company=company, name="Sam")

    home = c.get(reverse("webapp:mp_home")).content.decode()
    assert "Ravi" in home and "expired 1 days ago" in home and "10 days left" in home
    assert sw.overview(company)["expired"] == 1 and sw.overview(company)["soon"] == 1
    assert hr.run_daily_document_alerts() >= 2 and DocumentAlertLog.objects.filter(company=company).count() >= 2
    # renewing the ID clears its old alerts so it is warned again later
    c.post(reverse("webapp:mp_worker_edit", args=[ravi.id]), {
        "name": "Ravi", "trade": "Cleaner", "site": site.id, "employment_status": "active", "pay_basis": "hourly",
        "basic_pay": "6", "overtime_rate": "8", "id_no": "28435601234", "id_exp": (today + timedelta(days=365)).isoformat(),
        "passport_no": "P123", "passport_exp": (today - timedelta(days=1)).isoformat()})
    assert not DocumentAlertLog.objects.filter(document__document_type="ID / residence card").exists()

    # site timesheet for two days this month (or last month on the 1st)
    d1 = today if today.day > 1 else today - timedelta(days=1)
    d0 = d1 - timedelta(days=1) if d1.day > 1 else d1
    url = reverse("webapp:mp_attendance")
    c.post(url, {"site": site.id, "date": d1.isoformat(), f"s_{ravi.id}": "present", f"h_{ravi.id}": "",
                 f"ot_{ravi.id}": "2", f"s_{sam.id}": "present"})
    if d0 != d1:
        c.post(url, {"site": site.id, "date": d0.isoformat(), f"s_{ravi.id}": "half_day", f"s_{sam.id}": "absent"})
    mark = Attendance.objects.get(employee=ravi, date=d1)
    assert mark.site == site and mark.hours == Decimal("8") and mark.ot_hours == Decimal("2")
    assert c.post(url, {"site": site.id, "date": (today + timedelta(days=1)).isoformat(), f"s_{ravi.id}": "present"}).status_code == 302
    assert not Attendance.objects.filter(date=today + timedelta(days=1)).exists()

    start = sw.month_start(d1)
    rows = {r["employee"].name: r for r in sw.site_month(site, start)}
    ravi_hours = Decimal("12") if d0 != d1 else Decimal("8")
    assert rows["Ravi"]["hours"] == ravi_hours and rows["Ravi"]["ot"] == 2
    assert rows["Ravi"]["amount"] == ravi_hours * 15 + 2 * 20 and rows["Sam"]["rate"] == Decimal("25")

    # hourly pay in payroll: hours × rate, plus site OT; no absence deduction
    period = hr.month_period(company, start.strftime("%Y-%m"))
    run = hr.create_payroll_run(company=company, user=user, period=period)
    line = run.lines.get(employee=ravi)
    assert line.basic_pay == ravi_hours * 6 and line.overtime_hours == 2 and line.overtime_amount == 16 and line.absence_days == 0

    # one client invoice per site per month
    bill_url = reverse("webapp:mp_billing")
    c.post(bill_url, {"site": site.id, "m": start.strftime("%Y-%m")})
    billed = SiteInvoice.objects.get(site=site, month=start)
    assert billed.invoice.customer == site.client and billed.amount == sum(r["amount"] for r in rows.values())
    c.post(bill_url, {"site": site.id, "m": start.strftime("%Y-%m")})
    assert SiteInvoice.objects.filter(site=site).count() == 1
    assert "Billed" in c.get(bill_url + f"?m={start:%Y-%m}").content.decode()

    # take a worker off the site
    c.post(reverse("webapp:mp_site", args=[site.id]), {"action": "remove", "worker": [sam.id]})
    sam.refresh_from_db()
    assert sam.site is None


def test_joined_candidate_becomes_site_worker(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    job = _job(company, user, salary=Decimal("1800"))
    cand = svc.create_candidate(company=company, name="Faisal", trade="Electrician", passport_no="Z99",
                                passport_expiry=timezone.localdate() + timedelta(days=400))
    (placement,), _s = svc.submit(company=company, job=job, candidates=[cand])
    site = WorkSite.objects.create(company=company, name="Tower B", client=job.client, bill_rate=Decimal("12"))
    url = reverse("webapp:rec_placement", args=[placement.id])
    assert "Make site worker" not in c.get(url).content.decode()
    svc.move(placement, "deployed", joining_date=timezone.localdate())
    assert "Make site worker" in c.get(url).content.decode()
    c.post(url, {"action": "make_worker", "site": site.id})
    c.post(url, {"action": "make_worker", "site": site.id})
    worker = Employee.objects.get(company=company, candidate=cand)
    assert worker.site == site and worker.worker_type == "site" and worker.salary_structure.basic_pay == Decimal("1800")
    assert EmployeeDocument.objects.get(employee=worker, document_type="Passport").document_number == "Z99"
    assert "Already a site worker" in c.get(url).content.decode()


def test_other_business_types_do_not_see_site_workers(client, settings):
    from django.core.management import call_command
    from apps.tenants.models import Company
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Sweet Bakery", "business_type": "bakery", "country": "Qatar", "full_name": "Owner",
        "email": "b@bakery.test", "phone": "", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    assert Company.objects.filter(email="b@bakery.test").exists()
    assert client.get(reverse("webapp:mp_home")).status_code == 302
    assert reverse("webapp:mp_home") not in client.get(reverse("webapp:dashboard")).content.decode()
