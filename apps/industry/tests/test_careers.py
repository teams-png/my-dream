"""Careers website: open jobs and applications reach only the agency that owns the site."""
import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry import careers, recruitment as svc
from apps.industry.models import Candidate, CareersSite, Placement
from apps.notifications.models import Notification
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _signup(client, name, email):
    client.post(reverse("webapp:signup"), {
        "business_name": name, "business_type": "recruitment_agency", "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    return company, company.memberships.first().user


@pytest.fixture
def two_agencies(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    cache.clear()
    call_command("seed_platform")
    a_client, b_client = Client(), Client()
    a, a_user = _signup(a_client, "Gulf Manpower", "a@agency.test")
    b, b_user = _signup(b_client, "Other Agency", "b@agency.test")
    job = svc.create_job_order(company=a, user=a_user, client=Customer.objects.create(company=a, name="Secret Client LLC"),
                               position="Heavy Driver", vacancies=5, work_location="Doha, Qatar", salary=Decimal("2500"),
                               publish_online=True, public_summary="GCC licence required")
    hidden = svc.create_job_order(company=a, user=a_user, client=Customer.objects.create(company=a, name="Z"),
                                  position="Hidden Job", vacancies=1)
    site = careers.site_for(a)
    site.enabled = True
    site.save()
    return {"a": a, "b": b, "a_client": a_client, "b_client": b_client, "job": job, "hidden": hidden, "site": site}


def test_public_site_lists_only_published_jobs_and_hides_client(two_agencies):
    t = two_agencies
    page = Client().get(reverse("webapp:careers_home", args=[t["site"].slug]))
    html = page.content.decode()
    assert page.status_code == 200 and "Heavy Driver" in html and "Hidden Job" not in html
    assert "Secret Client" not in html
    detail = Client().get(reverse("webapp:careers_job", args=[t["site"].slug, t["job"].id])).content.decode()
    assert "GCC licence required" in detail and "Secret Client" not in detail
    assert Client().get(reverse("webapp:careers_job", args=[t["site"].slug, t["hidden"].id])).status_code == 404
    feed = Client().get(reverse("webapp:careers_jobs_json", args=[t["site"].slug])).json()
    assert [j["position"] for j in feed["jobs"]] == ["Heavy Driver"] and "Secret" not in json.dumps(feed)
    # a site that is switched off is not public
    t["site"].enabled = False
    t["site"].save()
    assert Client().get(reverse("webapp:careers_home", args=[t["site"].slug])).status_code == 404


def test_application_lands_only_in_the_owning_agency(two_agencies):
    t = two_agencies
    cv = SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf")
    resp = Client().post(reverse("webapp:careers_apply", args=[t["site"].slug]), {
        "job": t["job"].id, "name": "Rajesh Kumar", "phone": "+91 98765 43210", "passport_no": "p1234567",
        "nationality": "India", "experience_years": "6", "cv": cv, "message": "Have GCC licence"})
    assert resp.status_code == 302 and "/thanks/" in resp["Location"]
    cand = Candidate.objects.for_company(t["a"]).get(name="Rajesh Kumar")
    assert cand.source == "website" and cand.passport_no == "P1234567" and cand.cv and cand.status == "in_process"
    assert Placement.objects.get(candidate=cand).stage == "applied"
    assert not Candidate.objects.for_company(t["b"]).exists()
    assert Notification.objects.filter(company=t["a"], title__contains="Rajesh Kumar").exists()
    assert not Notification.objects.filter(company=t["b"], title__contains="Rajesh").exists()
    # the agency sees it on its dashboard and in the job pipeline; the other agency cannot open it
    assert "Rajesh Kumar" in t["a_client"].get(reverse("webapp:rec_home")).content.decode()
    assert "Applied online" in t["a_client"].get(reverse("webapp:rec_job_detail", args=[t["job"].id])).content.decode()
    assert t["b_client"].get(reverse("webapp:rec_candidate_detail", args=[cand.id])).status_code == 404


def test_same_person_applying_again_is_not_duplicated(two_agencies):
    t = two_agencies
    url = reverse("webapp:careers_apply", args=[t["site"].slug])
    Client().post(url, {"name": "Anil", "phone": "+977 9800000001", "passport_no": "N111"})
    Client().post(url, {"job": t["job"].id, "name": "Anil T", "phone": "9800000001", "passport_no": "n111",
                        "email": "anil@mail.test"})
    people = Candidate.objects.for_company(t["a"]).filter(passport_no="N111")
    assert people.count() == 1 and people.get().email == "anil@mail.test" and people.get().name == "Anil"
    assert Placement.objects.filter(candidate=people.get(), job_order=t["job"]).count() == 1


def test_validation_honeypot_and_rate_limit(two_agencies):
    t = two_agencies
    url = reverse("webapp:careers_apply", args=[t["site"].slug])
    bad = Client().post(url, {"name": "X", "phone": "12"})
    assert bad.status_code == 400 and not Candidate.objects.for_company(t["a"]).exists()
    Client().post(url, {"name": "Bot", "phone": "+97455555555", "passport_no": "B1", "company_website": "spam.com"})
    assert not Candidate.objects.for_company(t["a"]).filter(name="Bot").exists()
    exe = SimpleUploadedFile("cv.exe", b"MZ", content_type="application/octet-stream")
    resp = Client().post(url, {"name": "Exe", "phone": "+97455555556", "passport_no": "E1", "cv": exe})
    assert resp.status_code == 400 and not Candidate.objects.for_company(t["a"]).filter(name="Exe").exists()
    c = Client()
    for n in range(10):
        last = c.post(url, {"name": f"P{n}", "phone": f"+9745555{n:04d}", "passport_no": f"R{n}"})
    assert last.status_code == 400 and Candidate.objects.for_company(t["a"]).filter(name__startswith="P").count() < 10


def test_own_website_json_post_with_cors(two_agencies):
    t = two_agencies
    t["site"].allowed_origins = "https://www.gulfmanpower.com"
    t["site"].save()
    resp = Client().post(reverse("webapp:careers_apply", args=[t["site"].slug]) + "?format=json",
                         {"name": "Sam", "phone": "+97455551234", "passport_no": "S1", "job": t["job"].id},
                         HTTP_ORIGIN="https://www.gulfmanpower.com")
    assert resp.status_code == 201 and resp.json()["ok"] and resp["Access-Control-Allow-Origin"] == "https://www.gulfmanpower.com"
    other = Client().post(reverse("webapp:careers_apply", args=[t["site"].slug]) + "?format=json",
                          {"name": "Tom", "phone": "+97455551235", "passport_no": "T1"}, HTTP_ORIGIN="https://evil.test")
    assert "Access-Control-Allow-Origin" not in other


def test_settings_page_publish_jobs_and_slug(two_agencies):
    t = two_agencies
    c = t["a_client"]
    page = c.get(reverse("webapp:rec_website"))
    assert page.status_code == 200 and t["site"].slug in page.content.decode()
    c.post(reverse("webapp:rec_website"), {"action": "jobs", "publish": [t["hidden"].id]})
    t["job"].refresh_from_db(); t["hidden"].refresh_from_db()
    assert t["hidden"].publish_online and not t["job"].publish_online
    c.post(reverse("webapp:rec_website"), {"enabled": "on", "slug": "Gulf Jobs QA", "headline": "Work in Qatar",
                                           "accent_color": "red;}body{x", "allowed_origins": "", "services": "",
                                           "about": "", "countries": "Qatar, Saudi Arabia"})
    site = CareersSite.objects.get(company=t["a"])
    assert site.slug == "gulf-jobs-qa" and site.accent_color == "#0f766e"
    assert "Saudi Arabia" in Client().get(reverse("webapp:careers_home", args=["gulf-jobs-qa"])).content.decode()
    # the other agency cannot take the same address
    careers.site_for(t["b"])
    t["b_client"].post(reverse("webapp:rec_website"), {"slug": "gulf-jobs-qa", "accent_color": "#000000"})
    assert CareersSite.objects.get(company=t["b"]).slug != "gulf-jobs-qa"
