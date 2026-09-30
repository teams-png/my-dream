from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry import education as svc
from apps.industry.models import AttendanceMark, Course, Enrollment, FeeCharge
from apps.sales.models import SalesInvoice
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Bright Tuition", "business_type": "tuition_center", "country": "Qatar", "full_name": "Anu T",
        "email": "a@bright.test", "phone": "", "password": "Bright-Tuition-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="a@bright.test")
    user = company.memberships.first().user
    maths = Course.objects.create(company=company, name="Maths Grade 8", fee=Decimal("300"), billing="monthly", capacity=2)
    physics = Course.objects.create(company=company, name="Physics Grade 8", fee=Decimal("250"), billing="monthly")
    exam = Course.objects.create(company=company, name="Exam crash course", fee=Decimal("900"), billing="once")
    s1 = Customer.objects.create(company=company, name="Aisha", phone="5551")
    s2 = Customer.objects.create(company=company, name="Rahul", phone="5552")
    s3 = Customer.objects.create(company=company, name="Mei", phone="5553")
    return {"company": company, "user": user, "maths": maths, "physics": physics, "exam": exam,
            "s1": s1, "s2": s2, "s3": s3, "client": client}


def test_enrolment_rules_and_first_bill(school):
    d = school
    e = svc.enroll(company=d["company"], user=d["user"], course=d["maths"], student=d["s1"], start_date=date(2026, 9, 5),
                   discount_percent=10)
    assert e.fee == Decimal("270.00")
    assert FeeCharge.objects.get(enrollment=e).period == "2026-09"
    with pytest.raises(ValidationError):  # already enrolled
        svc.enroll(company=d["company"], user=d["user"], course=d["maths"], student=d["s1"], start_date=date(2026, 9, 5))
    svc.enroll(company=d["company"], user=d["user"], course=d["maths"], student=d["s2"], start_date=date(2026, 9, 5), bill_now=False)
    with pytest.raises(ValidationError):  # capacity 2
        svc.enroll(company=d["company"], user=d["user"], course=d["maths"], student=d["s3"], start_date=date(2026, 9, 5))
    once = svc.enroll(company=d["company"], user=d["user"], course=d["exam"], student=d["s3"], start_date=date(2026, 9, 7))
    assert FeeCharge.objects.get(enrollment=once).period == "once"


def test_month_run_one_invoice_per_student_and_idempotent(school):
    d = school
    for course in ("maths", "physics"):
        svc.enroll(company=d["company"], user=d["user"], course=d[course], student=d["s1"], start_date=date(2026, 9, 1), bill_now=False)
    svc.enroll(company=d["company"], user=d["user"], course=d["physics"], student=d["s2"], start_date=date(2026, 9, 1), bill_now=False)
    late = svc.enroll(company=d["company"], user=d["user"], course=d["physics"], student=d["s3"], start_date=date(2026, 11, 3),
                      bill_now=False)
    assert len(svc.due_for_month(d["company"], "2026-10")) == 3  # s3 starts in November
    invoices = svc.generate_month(company=d["company"], user=d["user"], key="2026-10")
    assert sorted(i.total for i in invoices) == [Decimal("250"), Decimal("550")]
    assert svc.generate_month(company=d["company"], user=d["user"], key="2026-10") == []
    svc.withdraw(late, end_date=date(2026, 10, 30))
    assert svc.due_for_month(d["company"], "2026-11") == [e for e in svc.due_for_month(d["company"], "2026-11")]
    assert len(svc.due_for_month(d["company"], "2026-11")) == 3  # the withdrawn student is not billed


def test_dues_and_month_summary(school):
    d = school
    svc.enroll(company=d["company"], user=d["user"], course=d["maths"], student=d["s1"], start_date=date(2026, 9, 1))
    svc.enroll(company=d["company"], user=d["user"], course=d["physics"], student=d["s2"], start_date=date(2026, 9, 1))
    from apps.sales import services as sales
    inv = SalesInvoice.objects.get(customer=d["s2"])
    sales.record_customer_payment(company=d["company"], user=d["user"], customer=d["s2"], amount=Decimal("250"),
                                  date=date(2026, 9, 2), invoice=inv)
    dues = svc.dues(d["company"])
    assert [(r["student"].name, r["due"]) for r in dues] == [("Aisha", Decimal("300.00"))]
    summary = svc.month_summary(d["company"], "2026-09")
    assert summary == {"billed": Decimal("550.00"), "collected": Decimal("250.00"), "outstanding": Decimal("300.00"), "count": 2}


def test_attendance(school):
    d = school
    a = svc.enroll(company=d["company"], user=d["user"], course=d["physics"], student=d["s1"], start_date=date(2026, 9, 1), bill_now=False)
    b = svc.enroll(company=d["company"], user=d["user"], course=d["physics"], student=d["s2"], start_date=date(2026, 9, 1), bill_now=False)
    svc.take_attendance(company=d["company"], user=d["user"], course=d["physics"], day=date(2026, 9, 2), present_ids=[a.pk])
    svc.take_attendance(company=d["company"], user=d["user"], course=d["physics"], day=date(2026, 9, 3), present_ids=[a.pk, b.pk])
    svc.take_attendance(company=d["company"], user=d["user"], course=d["physics"], day=date(2026, 9, 3), present_ids=[a.pk])  # corrected
    assert AttendanceMark.objects.count() == 4
    assert svc.attendance_rates(d["physics"]) == {a.pk: (2, 2), b.pk: (0, 2)}


def test_pages(school):
    d, c = school, school["client"]
    for name in ("education_home", "education_enroll", "education_fees", "education_dues", "education_course_add"):
        assert c.get(reverse(f"webapp:{name}")).status_code == 200, name
    resp = c.post(reverse("webapp:education_enroll"), {
        "course": d["maths"].id, "new_student_name": "Zara", "guardian_name": "Mr Khan", "guardian_phone": "5559",
        "start_date": "2026-09-01", "discount_percent": "0", "bill_now": "on"})
    assert resp.status_code == 302
    zara = Enrollment.objects.get(student__name="Zara")
    assert zara.student.phone == "5559" and FeeCharge.objects.filter(enrollment=zara).exists()
    page = c.get(reverse("webapp:education_course", args=[d["maths"].id]) + "?date=2026-09-02")
    assert page.status_code == 200 and "Zara" in page.content.decode()
    c.post(reverse("webapp:education_course", args=[d["maths"].id]), {"action": "attendance", "date": "2026-09-02", "present": [zara.id]})
    assert AttendanceMark.objects.get(enrollment=zara).present
    resp = c.post(reverse("webapp:education_fees"), {"month": "2026-10"})
    assert resp.status_code == 302 and FeeCharge.objects.filter(period="2026-10").count() == 1
