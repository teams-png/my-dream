"""Service contracts (AMC): visits planned as job cards, billing up front / recurring / per visit,
pause, cancel, renew, ending notice."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.finance.models import RecurringInvoice
from apps.industry import contracts
from apps.verticals.saloon.models import ServiceCase, ServiceContract

from .test_jobs import _clean_cache, _garage  # noqa: F401

pytestmark = pytest.mark.django_db


def _make(owner, staff, **extra):
    today = timezone.localdate()
    data = {"new_name": "Villa owner", "new_phone": "+974 5555 6666", "title": "AC maintenance – 4 units",
            "site_name": "Villa 12", "site_address": "Al Waab, St 20", "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=364)).isoformat(), "visit_every": "quarterly",
            "visit_minutes": 90, "staff": staff.id, "visit_task": "Clean filters, check gas",
            "contract_value": "1200", "billing": "upfront", "bill_amount": "", **extra}
    return owner.post(reverse("webapp:contract_new"), data)


def test_upfront_contract_plans_visits_and_bills_once():
    company, owner, staff = _garage("c1@t.qa", kind="ac_maintenance")
    r = _make(owner, staff)
    c = ServiceContract.objects.get(company=company)
    assert r.status_code == 302 and c.number.startswith("AMC-") and c.bill_amount == Decimal("1200")
    assert c.upfront_invoice and c.upfront_invoice.total == Decimal("1200")
    visit = ServiceCase.objects.get(contract=c)  # first visit is today → made at once
    assert visit.visit_no == 1 and visit.assigned_staff == staff and "visit 1" in visit.title
    assert c.next_visit_date - timezone.localdate() > timedelta(days=80)
    assert contracts.plan_visits(c) == 0  # nothing new within a week
    later = timezone.localdate() + timedelta(days=95)
    assert contracts.run_daily(today=later)["visits"] == 1
    assert ServiceCase.objects.filter(contract=c).count() == 2
    page = owner.get(reverse("webapp:contract_detail", args=[c.id])).content.decode()
    assert "AC maintenance" in page and "Villa 12" in page and "planned" in page
    assert "AMC-" in owner.get(reverse("webapp:contract_list")).content.decode()
    assert c.number in owner.get(reverse("webapp:service_case_detail", args=[visit.id])).content.decode()


def test_monthly_billing_per_visit_pause_cancel():
    company, owner, staff = _garage("c2@t.qa", kind="pest_control")
    _make(owner, staff, billing="monthly", title="Pest control monthly")
    c = ServiceContract.objects.get(company=company)
    assert c.bill_amount == Decimal("100.00") and c.recurring and c.recurring.frequency == "monthly"
    rec = RecurringInvoice.objects.get(pk=c.recurring_id)
    assert rec.lines.get().unit_price == Decimal("100.00") and rec.end_date == c.end_date
    contracts.pause(c)
    rec.refresh_from_db()
    assert not rec.is_active
    contracts.resume(c)
    rec.refresh_from_db()
    assert rec.is_active
    contracts.cancel(c)
    rec.refresh_from_db()
    c.refresh_from_db()
    assert c.status == "cancelled" and not rec.is_active and c.next_visit_date is None

    _make(owner, staff, billing="per_visit", title="Per visit service", visit_every="monthly")
    pv = ServiceContract.objects.get(company=company, title="Per visit service")
    visit = ServiceCase.objects.get(contract=pv)
    assert pv.bill_amount == Decimal("100.00") and visit.lines.get().unit_price == Decimal("100.00")


def test_renew_ending_notice_and_end():
    from apps.notifications.models import Notification
    company, owner, staff = _garage("c3@t.qa", kind="cleaning_company")
    today = timezone.localdate()
    _make(owner, staff, start_date=(today - timedelta(days=340)).isoformat(),
          end_date=(today + timedelta(days=20)).isoformat(), first_visit=(today + timedelta(days=200)).isoformat())
    assert ServiceContract.objects.filter(company=company).count() == 0  # first visit outside the dates: refused
    _make(owner, staff, start_date=(today - timedelta(days=340)).isoformat(),
          end_date=(today + timedelta(days=20)).isoformat(), visit_every="half_yearly")
    c = ServiceContract.objects.get(company=company)
    assert c in contracts.expiring(company)
    assert not ServiceCase.objects.filter(contract=c, scheduled_at__date__lt=today).exists()  # no back-dated visits
    contracts.run_daily()
    contracts.run_daily()
    assert Notification.objects.filter(company=company, title__contains=c.number).count() == 1
    owner.post(reverse("webapp:contract_action", args=[c.id]), {"do": "renew", "contract_value": "1500"})
    new = ServiceContract.objects.exclude(pk=c.pk).get(company=company)
    assert new.renewed_from == c and new.start_date == c.end_date + timedelta(days=1) and new.contract_value == Decimal("1500")
    assert c not in contracts.expiring(company)
    contracts.run_daily(today=c.end_date + timedelta(days=1))
    c.refresh_from_db()
    assert c.status == "ended"
    # another business cannot open it
    _company2, other, _s = _garage("c4@t.qa", kind="cleaning_company")
    assert other.get(reverse("webapp:contract_detail", args=[c.id])).status_code == 404
