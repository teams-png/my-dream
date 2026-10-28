"""Gym counter: join a new member with payment, member card with body progress, quick check-in, renewal, reports."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.industry.tests.test_jobs import _clean_cache, _garage  # noqa: F401
from apps.sales.models import CustomerPayment, SalesInvoice
from apps.verticals.gym.models import Attendance, GymMember
from apps.verticals.gym.services import create_membership_plan

pytestmark = pytest.mark.django_db


def test_join_check_in_measure_renew_and_report():
    company, owner, trainer = _garage("gym1@t.qa", kind="gym")
    monthly = create_membership_plan(company=company, name="Monthly", duration_days=30, price=Decimal("1200"))
    today = timezone.localdate()
    r = owner.post(reverse("webapp:member_enroll"), {
        "new_name": "Arjun Das", "new_phone": "+974 5555 7788", "membership_plan": monthly.id,
        "join_date": today.isoformat(), "admission_fee": "500", "trainer": trainer.id, "goal": "Weight loss",
        "method": "bank"})
    member = GymMember.objects.get(company=company, customer__name="Arjun Das")
    assert r.status_code == 302 and member.trainer == trainer and member.member_no.startswith("GM-")
    invoice = SalesInvoice.objects.get(company=company, customer=member.customer)
    assert invoice.total == Decimal("1700") and invoice.status == "paid"
    assert CustomerPayment.objects.get(invoice=invoice).method == "bank"

    att = owner.get(reverse("webapp:attendance_today")).content.decode()
    assert "Arjun Das" in att and "Check in" in att
    owner.post(reverse("webapp:attendance_check_in", args=[member.id]))
    owner.post(reverse("webapp:attendance_check_in", args=[member.id]))
    assert Attendance.objects.filter(member=member).count() == 1
    assert owner.get(reverse("webapp:attendance_check_in", args=[member.id])).status_code == 405

    url = reverse("webapp:member_measure", args=[member.id])
    owner.post(url, {"date": (today - timedelta(days=20)).isoformat(), "weight_kg": "86", "height_cm": "175", "waist_cm": "96"})
    owner.post(url, {"date": today.isoformat(), "weight_kg": "82.5"})
    card = owner.get(reverse("webapp:member_detail", args=[member.id])).content.decode()
    assert "Body progress" in card and "-3.5 kg" in card and "26.9" in card and invoice.invoice_number in card

    GymMember.objects.filter(pk=member.pk).update(membership_end=today - timedelta(days=2))
    lst = owner.get(reverse("webapp:member_list") + "?tab=expired").content.decode()
    assert "Arjun Das" in lst and "Ended 2 days ago" in lst and "wa.me/" in lst
    member.refresh_from_db()
    assert member.status == "expired"
    Attendance.objects.filter(member=member).update(check_out=timezone.now())
    owner.post(reverse("webapp:attendance_check_in", args=[member.id]))
    assert Attendance.objects.filter(member=member).count() == 1

    owner.post(reverse("webapp:member_renew", args=[member.id]), {
        "membership_plan": monthly.id, "start_date": today.isoformat(), "method": "cash"})
    member.refresh_from_db()
    assert member.status == "active" and member.membership_end == today + timedelta(days=30)
    rep = owner.get(reverse("webapp:gym_reports")).content.decode()
    assert "Fees this month" in rep and ("2,900.00" in rep or "2900.00" in rep)
