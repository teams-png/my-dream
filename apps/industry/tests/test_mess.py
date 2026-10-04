"""Restaurant mess: monthly plans, members, daily meals, mess cut and monthly bills."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry import mess as svc
from apps.industry.models import MessCharge, MessMeal, MessMember, MessPlan
from apps.sales.models import SalesInvoice
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))


def _signup(code, email):
    client = Client(REMOTE_ADDR=f"10.12.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    return company, client, company.memberships.get(role__name="Owner").user


@pytest.fixture(autouse=True)
def platform():
    cache.clear()
    call_command("seed_platform")


def _plan(company, **kw):
    data = {"name": "Full mess", "monthly_fee": Decimal("450"), "leave_refund_per_day": Decimal("12"), "min_leave_days": 3}
    data.update(kw)
    return MessPlan.objects.create(company=company, **data)


def test_join_mid_month_bills_only_the_days_left():
    company, _c, owner = _signup("restaurant", "m1@t.qa")
    plan = _plan(company)
    customer = Customer.objects.create(company=company, name="Anoop", phone="55512345")
    member = svc.join(company=company, user=owner, plan=plan, customer=customer, start_date=date(2026, 9, 16))
    charge = MessCharge.objects.get(member=member, period="2026-09")
    assert member.number == "M-001" and charge.amount == Decimal("225.00")  # 15 of 30 days
    assert SalesInvoice.objects.get(pk=charge.invoice_id).total >= Decimal("225.00")
    with pytest.raises(ValidationError):
        svc.join(company=company, user=owner, plan=plan, customer=customer, start_date=date(2026, 9, 20))


def test_meals_are_ticked_once_and_only_when_allowed():
    company, _c, owner = _signup("restaurant", "m2@t.qa")
    lunch_only = _plan(company, name="Lunch only", breakfast=False, dinner=False, monthly_fee=Decimal("200"))
    member = svc.join(company=company, user=owner, plan=lunch_only, bill_now=False, start_date=date(2026, 10, 1),
                      customer=Customer.objects.create(company=company, name="Biju"))
    day = date(2026, 10, 5)
    svc.serve(company=company, user=owner, member=member, meal="lunch", day=day)
    with pytest.raises(ValidationError):
        svc.serve(company=company, user=owner, member=member, meal="lunch", day=day)  # twice
    with pytest.raises(ValidationError):
        svc.serve(company=company, user=owner, member=member, meal="dinner", day=day)  # not in plan
    svc.add_leave(company=company, member=member, from_date=date(2026, 10, 10), to_date=date(2026, 10, 14))
    with pytest.raises(ValidationError):
        svc.serve(company=company, user=owner, member=member, meal="lunch", day=date(2026, 10, 12))  # mess cut
    with pytest.raises(ValidationError):
        svc.add_leave(company=company, member=member, from_date=date(2026, 10, 13), to_date=date(2026, 10, 15))
    count = svc.today(company, date(2026, 10, 12))
    assert {c["meal"]: c["expected"] for c in count["meals"]} == {"breakfast": 0, "lunch": 0, "dinner": 0}
    assert svc.today(company, day)["meals"][1] == {"meal": "lunch", "expected": 1, "served": 1, "left": 0}


def test_last_months_mess_cut_comes_off_the_bill_and_runs_once():
    company, _c, owner = _signup("restaurant", "m3@t.qa")
    plan = _plan(company)
    a = svc.join(company=company, user=owner, plan=plan, bill_now=False, start_date=date(2026, 8, 1),
                 customer=Customer.objects.create(company=company, name="Arun"))
    b = svc.join(company=company, user=owner, plan=plan, bill_now=False, start_date=date(2026, 8, 1),
                 customer=Customer.objects.create(company=company, name="Faisal"), monthly_fee=Decimal("400"))
    svc.add_leave(company=company, member=a, from_date=date(2026, 9, 25), to_date=date(2026, 10, 4))  # 6 days in Sept
    svc.add_leave(company=company, member=b, from_date=date(2026, 9, 10), to_date=date(2026, 9, 11))  # too short
    invoices = svc.generate_month(company=company, user=owner, key="2026-10")
    assert len(invoices) == 2
    ca, cb = MessCharge.objects.get(member=a, period="2026-10"), MessCharge.objects.get(member=b, period="2026-10")
    assert (ca.leave_days, ca.refund, ca.amount) == (6, Decimal("72.00"), Decimal("378.00"))
    assert (cb.leave_days, cb.refund, cb.amount) == (0, Decimal("0"), Decimal("400.00"))
    assert svc.generate_month(company=company, user=owner, key="2026-10") == []
    assert [r["member"] for r in svc.dues(company)] == [b, a]


def test_pages_and_serving_from_the_screen():
    company, client, owner = _signup("restaurant", "m4@t.qa")
    assert "Mess" in client.get(reverse("webapp:dashboard")).content.decode()
    client.post(reverse("webapp:mess_plan_add"), {"name": "Full mess", "breakfast": "on", "lunch": "on", "dinner": "on",
                                                  "monthly_fee": "450", "leave_refund_per_day": "0", "min_leave_days": "3",
                                                  "is_active": "on"})
    plan = MessPlan.objects.for_company(company).get()
    from django.utils import timezone
    response = client.post(reverse("webapp:mess_join"), {"plan": plan.id, "new_customer_name": "Rashid",
                                                         "new_customer_phone": "55500011",
                                                         "start_date": timezone.localdate().isoformat(), "bill_now": "on"})
    member = MessMember.objects.for_company(company).get()
    assert response.status_code == 302 and member.charges.count() == 1
    client.post(reverse("webapp:mess_home"), {"member": member.id, "meal": "lunch"})
    assert MessMeal.objects.filter(member=member, meal="lunch").exists()
    page = client.get(reverse("webapp:mess_home")).content.decode()
    assert "Rashid" in page and "M-001" in page
    for name in ("mess_plans", "mess_bills", "mess_dues"):
        assert client.get(reverse(f"webapp:{name}")).status_code == 200
    assert client.get(reverse("webapp:mess_member", args=[member.id])).status_code == 200
    client.post(reverse("webapp:mess_home"), {"member": member.id, "meal": "lunch", "action": "undo"})
    assert not MessMeal.objects.filter(member=member).exists()


def test_mess_is_only_for_food_businesses():
    _company, client, _owner = _signup("mobile_shop", "m5@t.qa")
    assert client.get(reverse("webapp:mess_home")).status_code == 302
