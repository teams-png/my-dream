"""Advanced features behind ON/OFF switches (HR settings): all off by default and hidden from the menus;
WPS salary file, gratuity & final settlement, vacation & ticket, camps (cost in site profit), visa quota and
sub-agent commission."""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.employees import advanced, services as hr
from apps.employees import site_workers as sw
from apps.employees.models import Camp, Employee, EmployeeDocument, FinalSettlement, HRSettings, Vacation, WorkSite
from apps.industry import recruitment as svc
from apps.industry.models import VisaQuota
from apps.suppliers.models import Supplier

from .test_recruitment import agency  # noqa: F401

pytestmark = pytest.mark.django_db


def _switch_on(c, *codes, **extra):
    data = {"off": ["4"], "deduct_absence": "on", "advanced": "1", "extra": list(codes),
            "gratuity_days_per_year": "21", "vacation_days_per_year": "21", "ticket_every_months": "24"}
    data.update(extra)
    c.post(reverse("webapp:hr_settings"), data)


def test_everything_is_off_by_default_and_hidden(agency):
    company, c = agency["company"], agency["client"]
    assert advanced.enabled(company) == set()
    home = c.get(reverse("webapp:dashboard")).content.decode()
    assert reverse("webapp:rec_visa_quotas") not in home and reverse("webapp:mp_camps") not in home
    assert c.get(reverse("webapp:hr_vacations")).status_code == 404
    page = c.get(reverse("webapp:hr_settings")).content.decode()
    assert "Advanced features" in page and "WPS salary file" in page and "Visa quota" in page
    _switch_on(c, "visa_quota", "camps", "bogus")
    assert advanced.enabled(company) == {"visa_quota", "camps"}
    home = c.get(reverse("webapp:dashboard")).content.decode()
    assert reverse("webapp:rec_visa_quotas") in home and reverse("webapp:mp_camps") in home
    assert reverse("webapp:rec_agents") not in home


def test_wps_file_settlement_and_vacation(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    _switch_on(c, "wps", "settlement", "vacation", wps_employer_eid="12345", wps_payer_bank="qnb",
               wps_payer_iban="QA58QNBA000000000000693123456")
    joined = timezone.localdate() - timedelta(days=int(365 * 3))
    c.post(reverse("webapp:staff_add"), {"name": "Anu", "role_title": "Accountant", "employment_status": "active",
                                         "basic_pay": "3000", "allowance": "1000", "joined_date": joined.isoformat(),
                                         "bank_short_name": "CBQ", "iban": "QA00CBQ1234", "visa_id": "V1"})
    anu = Employee.objects.get(name="Anu")
    assert anu.iban == "QA00CBQ1234"
    EmployeeDocument.objects.create(company=company, employee=anu, document_type="ID / residence card",
                                    document_number="28435601234")
    c.post(reverse("webapp:staff_add"), {"name": "Bilal", "employment_status": "active", "basic_pay": "2000"})

    # WPS file from an approved payroll
    period = hr.month_period(company, timezone.localdate().strftime("%Y-%m"))
    run = hr.create_payroll_run(company=company, user=user, period=period)
    hr.post_payroll(company=company, user=user, payroll_run=run, date=timezone.localdate())
    assert reverse("webapp:hr_wps", args=[run.id]) in c.get(reverse("webapp:hr_payroll")).content.decode()
    problems = c.get(reverse("webapp:hr_wps", args=[run.id])).content.decode()
    assert "Bilal" in problems and "Download anyway" in problems  # Bilal has no QID / bank / IBAN
    resp = c.get(reverse("webapp:hr_wps", args=[run.id]) + "?force=1")
    assert resp["Content-Disposition"].startswith('attachment; filename="SIF_12345_QNB_')
    rows = list(csv.reader(io.StringIO(resp.content.decode())))
    assert rows[0][0] == "Employer EID" and rows[1][0] == "12345" and rows[1][9] == "2"
    anu_row = next(r for r in rows[3:] if r[3] == "Anu")
    assert anu_row[1] == "28435601234" and anu_row[4] == "CBQ" and anu_row[8] == "4000.00"

    # vacation: 3 years × 21 days earned; take 30 with a ticket
    start = timezone.localdate() - timedelta(days=40)
    c.post(reverse("webapp:hr_vacations"), {"action": "add", "employee": anu.id, "start": start.isoformat(),
                                            "end": (start + timedelta(days=29)).isoformat(), "ticket": "on",
                                            "ticket_amount": "1500"})
    v = Vacation.objects.get(employee=anu)
    board = c.get(reverse("webapp:hr_vacations")).content.decode()
    assert "Late back" in board and "Anu" in board  # due back 10 days ago, not marked back
    c.post(reverse("webapp:hr_vacations"), {"action": "returned", "vacation": v.id, "date": timezone.localdate().isoformat()})
    v.refresh_from_db()
    assert v.returned_on == timezone.localdate()
    bal = advanced.vacation_balance(anu)
    assert bal["taken"] == 30 and bal["balance"] == bal["earned"] - 30 and not bal["ticket_due"]

    # final settlement: gratuity 3000/30 × 21 × ~3 years; advance recovered; recorded and the person leaves
    hr.give_advance(company=company, user=user, employee=anu, amount=Decimal("500"), date=timezone.localdate(),
                    monthly_deduction=Decimal("100"))
    last = timezone.localdate()
    url = reverse("webapp:settlement_new", args=[anu.id])
    preview = c.get(url + f"?last_day={last.isoformat()}").content.decode()
    assert "Gratuity" in preview and "Net to pay" in preview
    c.post(url, {"last_day": last.isoformat(), "reason": "resigned", "ticket_amount": "0", "save": "1"})
    s = FinalSettlement.objects.get(employee=anu)
    years = advanced.service_years(anu, last)
    assert s.years == years and s.gratuity == (Decimal("3000") / 30 * 21 * years).quantize(Decimal("0.01"))
    assert s.advance_deduction == Decimal("500") and s.net == s.gratuity + s.salary_amount + s.leave_amount - Decimal("500")
    c.post(reverse("webapp:settlement_detail", args=[s.id]), {"action": "pay", "method": "bank"})
    s.refresh_from_db()
    anu.refresh_from_db()
    assert s.status == "paid" and s.journal_entry is not None and not anu.is_active and anu.leaving_date == last
    assert hr.employee_advance_balance(company=company, employee=anu) == 0
    assert c.get(reverse("webapp:settlement_detail", args=[s.id]) + "?print=1").status_code == 200

    # under a year: no gratuity
    young = Employee.objects.create(company=company, name="New", salary=Decimal("2000"),
                                    joined_date=timezone.localdate() - timedelta(days=100))
    assert advanced.gratuity(young, timezone.localdate())[1] == 0


def test_camps_visa_quota_and_sub_agents(agency):
    company, user, c = agency["company"], agency["user"], agency["client"]
    _switch_on(c, "camps", "visa_quota", "sub_agents")
    # camp cost goes into site profit
    site = WorkSite.objects.create(company=company, name="Mall", client=Customer.objects.create(company=company, name="M"),
                                   bill_basis="day", bill_rate=Decimal("100"))
    c.post(reverse("webapp:mp_worker_add"), {"name": "Ravi", "trade": "Cleaner", "site": site.id, "employment_status": "active",
                                             "pay_basis": "daily", "basic_pay": "50"})
    ravi = Employee.objects.get(name="Ravi")
    c.post(reverse("webapp:mp_camps"), {"action": "save", "name": "Camp A", "capacity": "10", "monthly_cost": "1000",
                                        "food_per_head": "200", "transport_per_head": "50"})
    camp = Camp.objects.get(company=company)
    c.post(reverse("webapp:mp_camps"), {"action": "move_in", "camp": camp.id, "worker": [ravi.id]})
    ravi.refresh_from_db()
    assert ravi.camp == camp and advanced.head_cost(camp) == Decimal("1250.00")
    d = timezone.localdate() if timezone.localdate().day > 1 else timezone.localdate() - timedelta(days=1)
    c.post(reverse("webapp:mp_attendance"), {"site": site.id, "date": d.isoformat(), f"s_{ravi.id}": "present"})
    start = sw.month_start(d)
    row = sw.profit_report(company, start)[0][0].rows[0]
    month_days = sw.working_days(company, start)
    assert row["camp"] == (Decimal("1250") / month_days).quantize(Decimal("0.01"))
    assert row["cost"] == Decimal("50") + row["camp"]
    assert "Camp" in c.get(reverse("webapp:mp_profit") + f"?m={start:%Y-%m}").content.decode()

    # visa quota: 2 approved, one used by a placement
    c.post(reverse("webapp:rec_visa_quotas"), {"action": "save", "reference": "BV-2026-77", "profession": "Electrician",
                                               "nationality": "India", "gender": "any", "total": "2",
                                               "expiry_date": (timezone.localdate() + timedelta(days=20)).isoformat()})
    quota = VisaQuota.objects.get(company=company)
    agent = Supplier.objects.create(company=company, name="Kochi Agency")
    job = svc.create_job_order(company=company, user=user, client=Customer.objects.create(company=company, name="Client"),
                               position="Electrician", vacancies=2)
    cand = svc.create_candidate(company=company, name="Faisal", agent=agent)
    (p,), _s = svc.submit(company=company, job=job, candidates=[cand])
    page = c.get(reverse("webapp:rec_placement", args=[p.id])).content.decode()
    assert "BV-2026-77" in page and "Commission for" in page
    c.post(reverse("webapp:rec_placement", args=[p.id]), {"action": "extras", "visa_quota": quota.id, "agent_commission": "300"})
    p.refresh_from_db()
    assert p.visa_quota == quota and p.agent_commission == Decimal("300")
    q = advanced.visa_quotas(company)[0]
    assert q.used == 1 and q.left == 1 and q.expiring
    assert "1/2" in c.get(reverse("webapp:rec_visa_quotas")).content.decode()

    # sub-agent: owed only once the candidate joined; paid = agent costs
    assert advanced.agent_statement(company)[0]["owed"] == 0
    svc.move(p, "deployed", joining_date=timezone.localdate())
    svc.add_cost(company=company, user=user, placement=p, cost_type="agent", amount=Decimal("100"), paid_to="Kochi Agency")
    row = advanced.agent_statement(company)[0]
    assert row["owed"] == Decimal("300") and row["paid"] == Decimal("100") and row["balance"] == Decimal("200")
    assert "Kochi Agency" in c.get(reverse("webapp:rec_agents")).content.decode()
