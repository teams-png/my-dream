"""Recruitment agency: clients, job orders, candidates, the pipeline to joining, billing and costs."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.expenses.models import Expense
from apps.industry import recruitment as svc
from apps.industry.models import Candidate, JobOrder, Placement
from apps.notifications.models import Notification
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def agency(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Gulf Manpower", "business_type": "recruitment_agency", "country": "Qatar",
        "full_name": "Owner", "email": "hr@agency.test", "phone": "", "password": "Gold-Shop-2026!",
        "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="hr@agency.test")
    return {"company": company, "user": company.memberships.first().user, "client": client}


def test_menu_dashboard_and_all_pages_open(agency):
    c = agency["client"]
    home = c.get(reverse("webapp:dashboard")).content.decode()
    assert reverse("webapp:rec_clients") in home and reverse("webapp:rec_candidates") in home
    assert "Recruitment Projects" not in home  # the old generic project menu is replaced
    for name in ("rec_home", "rec_clients", "rec_jobs", "rec_job_add", "rec_candidates", "rec_candidate_add"):
        assert c.get(reverse(f"webapp:{name}")).status_code == 200, name


def test_add_client_then_job_order_with_new_client_inline(agency):
    c, company = agency["client"], agency["company"]
    resp = c.post(reverse("webapp:rec_clients"), {"name": "Al Noor Contracting", "phone": "+97444445555",
                                                  "email": "", "address": "Doha", "payment_terms_days": 30, "then": "job"})
    client_obj = Customer.objects.for_company(company).get(name="Al Noor Contracting")
    assert resp.status_code == 302 and f"client={client_obj.id}" in resp["Location"]
    c.post(reverse("webapp:rec_job_add"), {"client": "", "new_client_name": "Qatar Hotels", "new_client_phone": "5555",
                                           "position": "Waiter", "vacancies": 3, "gender": "any",
                                           "fee_per_placement": "1500", "guarantee_days": 90})
    job = JobOrder.objects.for_company(company).get(position="Waiter")
    assert job.client.name == "Qatar Hotels" and job.number.startswith("JO-")
    page = c.get(reverse("webapp:rec_clients")).content.decode()
    assert "Al Noor Contracting" in page and "Qatar Hotels" in page


def test_pipeline_to_joining_billing_costs_and_profit(agency):
    c, company, user = agency["client"], agency["company"], agency["user"]
    client_obj = Customer.objects.create(company=company, name="Al Noor", phone="97444445555")
    job = svc.create_job_order(company=company, user=user, client=client_obj, position="Electrician", vacancies=1,
                               fee_per_placement=Decimal("2000"), salary=Decimal("1800"))
    cv = SimpleUploadedFile("cv.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    c.post(reverse("webapp:rec_candidate_add") + f"?job={job.id}", {
        "name": "Rajesh Kumar", "phone": "+919876543210", "trade": "Electrician", "nationality": "India",
        "passport_no": "p1234567", "passport_expiry": (date.today() + timedelta(days=60)).isoformat(), "cv": cv})
    raj = Candidate.objects.for_company(company).get(name="Rajesh Kumar")
    assert raj.passport_no == "P1234567" and raj.status == "in_process" and raj.cv
    assert c.get(reverse("webapp:rec_candidate_cv", args=[raj.id])).status_code == 200
    # duplicate passport is refused
    c.post(reverse("webapp:rec_candidate_add"), {"name": "Copy", "passport_no": "P1234567"})
    assert not Candidate.objects.for_company(company).filter(name="Copy").exists()

    # quick-add a second candidate straight from the job page
    c.post(reverse("webapp:rec_job_detail", args=[job.id]), {"action": "submit", "new_name": "Anil", "new_phone": "91999"})
    assert job.placements.count() == 2
    board = c.get(reverse("webapp:rec_job_detail", args=[job.id])).content.decode()
    assert "Rajesh Kumar" in board and "Anil" in board

    placement = Placement.objects.get(job_order=job, candidate=raj)
    when = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT10:00")
    url = reverse("webapp:rec_placement", args=[placement.id])
    c.post(url, {"action": "update", "stage": "interview", "interview_at": when})
    page = c.get(url).content.decode()
    assert "wa.me/919876543210" in page
    c.post(url, {"action": "update", "stage": "medical", "medical_result": "fit", "medical_date": date.today().isoformat()})
    c.post(url, {"action": "update", "stage": "visa", "visa_number": "V-1", "visa_expiry": (date.today() + timedelta(days=10)).isoformat()})
    c.post(url, {"action": "update", "stage": "deployed"})
    placement.refresh_from_db(); raj.refresh_from_db(); job.refresh_from_db()
    assert placement.stage == "deployed" and placement.joining_date == date.today()
    assert placement.guarantee_until == date.today() + timedelta(days=90)
    assert raj.status == "placed" and job.status == "filled"
    # no second person can join a 1-vacancy job
    anil = Placement.objects.get(job_order=job, candidate__name="Anil")
    with pytest.raises(Exception):
        svc.move(anil, "deployed")

    c.post(url, {"action": "bill_client", "amount": "2000"})
    c.post(url, {"action": "bill_client", "amount": "2000"})  # second click does nothing
    c.post(url, {"action": "bill_candidate", "amount": "300"})
    c.post(url, {"action": "cost", "cost_type": "ticket", "amount": "900", "paid_to": "Qatar Airways", "method": "cash"})
    placement.refresh_from_db()
    assert placement.invoice.total == Decimal("2000") and placement.invoice.customer == client_obj
    assert placement.candidate_invoice.customer.name == "Rajesh Kumar"
    assert Expense.objects.for_company(company).filter(category__name="Recruitment costs", amount=900).exists()
    assert svc.placement_money(placement)["profit"] == Decimal("1400")
    # the candidate's billing record does not show up as a client
    assert "Rajesh Kumar" not in c.get(reverse("webapp:rec_clients")).content.decode()
    assert c.get(reverse("webapp:rec_candidates") + "?format=xlsx")["Content-Type"].endswith("spreadsheetml.sheet")


def test_unfit_medical_rejects_and_frees_the_candidate(agency):
    company, user = agency["company"], agency["user"]
    job = svc.create_job_order(company=company, user=user, client=Customer.objects.create(company=company, name="X"),
                               position="Driver", vacancies=2)
    cand = svc.create_candidate(company=company, name="Sam")
    (placement,), _ = svc.submit(company=company, job=job, candidates=[cand])
    svc.move(placement, "medical", medical_result="unfit")
    placement.refresh_from_db(); cand.refresh_from_db()
    assert placement.stage == "rejected" and cand.status == "available"


def test_nightly_reminders(agency):
    company, user = agency["company"], agency["user"]
    svc.create_candidate(company=company, name="Old Passport", passport_expiry=date.today() + timedelta(days=20))
    job = svc.create_job_order(company=company, user=user, client=Customer.objects.create(company=company, name="Y"),
                               position="Cook", vacancies=1)
    cand = svc.create_candidate(company=company, name="Visa Guy")
    (placement,), _ = svc.submit(company=company, job=job, candidates=[cand])
    svc.move(placement, "visa", visa_expiry=date.today() + timedelta(days=5))
    assert svc.daily_reminders(company) == 2
    assert svc.daily_reminders(company) == 0
    titles = list(Notification.objects.filter(company=company).values_list("title", flat=True))
    assert any("Passport expiring: Old Passport" in t for t in titles) and any("Visa Guy" in t for t in titles)


def test_generic_project_form_can_add_a_new_client(client, settings):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Events Co", "business_type": "event_management", "country": "Qatar", "full_name": "O",
        "email": "ev@test.qa", "phone": "", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="ev@test.qa")
    client.post(reverse("webapp:project_add"), {"name": "Wedding", "client": "", "new_client_name": "Fatima",
                                                "new_client_phone": "5551", "start_date": date.today().isoformat(),
                                                "budget": "0", "contract_value": "5000"})
    from apps.verticals.construction.models import Project
    assert Project.objects.for_company(company).get(name="Wedding").client.name == "Fatima"
