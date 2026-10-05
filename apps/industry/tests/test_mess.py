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
    assert svc.today(company, day)["meals"][1] == {"meal": "lunch", "expected": 1, "served": 1, "left": 0,
                                                    "delivery": 0, "dine_in": 1}


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


# ------------------------------------------------------------------ extras, weekly menu, delivery

def _member(company, owner, name="Shafeek", plan=None, **kw):
    plan = plan or _plan(company, leave_refund_per_day=Decimal("0"))
    return svc.join(company=company, user=owner, plan=plan, bill_now=False, start_date=date(2026, 9, 1),
                    customer=Customer.objects.create(company=company, name=name, phone="55511122"), **kw)


def test_extras_go_on_the_next_monthly_bill_once():
    from apps.industry.models import MessExtra, MessExtraItem
    company, _c, owner = _signup("restaurant", "m6@t.qa")
    member = _member(company, owner)
    chicken = MessExtraItem.objects.create(company=company, name="Chicken curry", price=Decimal("5"))
    for day in (3, 10, 17):
        svc.add_extra(company=company, user=owner, member=member, item=chicken, day=date(2026, 9, day), meal="lunch")
    svc.add_extra(company=company, user=owner, member=member, name="Fresh juice", unit_price="4", quantity=2,
                  day=date(2026, 9, 20))
    later = svc.add_extra(company=company, user=owner, member=member, item=chicken, day=date(2026, 10, 3))
    with pytest.raises(ValidationError):
        svc.add_extra(company=company, user=owner, member=member, name="Egg", unit_price="1", quantity=0)
    with pytest.raises(ValidationError):
        svc.add_extra(company=company, user=owner, member=member, name="", unit_price="1")
    with pytest.raises(ValidationError):
        svc.add_extra(company=company, user=owner, member=member, name="Egg", unit_price="-1")
    assert svc.pending_total(member, date(2026, 10, 1)) == Decimal("23.00")

    [inv] = svc.generate_month(company=company, user=owner, key="2026-10", on=date(2026, 10, 1))
    charge = MessCharge.objects.get(member=member, period="2026-10")
    assert charge.extras == Decimal("23.00") and charge.amount == Decimal("473.00")
    lines = {l.product.name: (l.quantity, l.unit_price) for l in inv.lines.select_related("product")}
    assert lines["Mess extra – Chicken curry"] == (Decimal("3"), Decimal("5.00"))
    assert lines["Mess extra – Fresh juice"] == (Decimal("2"), Decimal("4.00"))
    assert inv.total >= Decimal("473.00")
    assert MessExtra.objects.filter(member=member, invoice=inv).count() == 4
    later.refresh_from_db()
    assert later.invoice_id is None  # given after the bill date: waits for November
    billed = MessExtra.objects.filter(invoice=inv).first()
    with pytest.raises(ValidationError):
        svc.remove_extra(billed)
    svc.remove_extra(later)
    assert not MessExtra.objects.filter(pk=later.pk).exists()


def test_members_who_left_get_a_bill_for_just_their_extras():
    company, _c, owner = _signup("restaurant", "m7@t.qa")
    member = _member(company, owner)
    svc.add_extra(company=company, user=owner, member=member, name="Fish fry", unit_price="6", day=date(2026, 9, 28))
    svc.set_status(member, "ended", on=date(2026, 9, 30))
    with pytest.raises(ValidationError):
        svc.add_extra(company=company, user=owner, member=member, name="Egg", unit_price="1")
    invoices = svc.generate_month(company=company, user=owner, key="2026-10", on=date(2026, 10, 1))
    assert len(invoices) == 1 and invoices[0].total >= Decimal("6.00")
    assert not MessCharge.objects.filter(member=member, period="2026-10").exists()
    assert [r["member"] for r in svc.dues(company)] == [member]
    assert svc.generate_month(company=company, user=owner, key="2026-10", on=date(2026, 10, 1)) == []
    assert svc.bill_extras(company=company, user=owner, member=member) is None


def test_weekly_menu_per_plan():
    company, _c, owner = _signup("restaurant", "m8@t.qa")
    full = _plan(company)
    lunch_only = _plan(company, name="Lunch only", breakfast=False, dinner=False, monthly_fee=Decimal("200"))
    svc.save_menu(full, {(0, "breakfast"): "Puttu,  kadala", (0, "lunch"): "Rice, sambar", (4, "lunch"): "Biryani"})
    svc.save_menu(lunch_only, {(0, "lunch"): "Rice, fish curry", (0, "dinner"): "Not in this plan"})
    assert svc.menu_grid(full) == {(0, "breakfast"): "Puttu, kadala", (0, "lunch"): "Rice, sambar", (4, "lunch"): "Biryani"}
    assert svc.menu_grid(lunch_only) == {(0, "lunch"): "Rice, fish curry"}
    svc.save_menu(full, {(4, "lunch"): "  "})
    assert (4, "lunch") not in svc.menu_grid(full)
    monday = date(2026, 10, 5)
    today = svc.menu_for_day(company, monday)
    assert [(r["plan"].name, r["meals"]) for r in today] == [
        ("Full mess", [("breakfast", "Puttu, kadala"), ("lunch", "Rice, sambar")]),
        ("Lunch only", [("lunch", "Rice, fish curry")])]
    text = svc.menu_text(full, company_name="Malabar")
    assert "*Monday*" in text and "Lunch: Rice, sambar" in text
    assert svc.menu_text(full, day=monday).count("\n") >= 2


def test_delivery_or_eat_at_the_shop():
    company, _c, owner = _signup("restaurant", "m9@t.qa")
    plan = _plan(company)
    office = _member(company, owner, name="Office boy", plan=plan, delivery_meals=["lunch", "bogus"],
                     delivery_address="Al Noor Trading, 3rd floor")
    walkin = _member(company, owner, name="Walk in", plan=plan)
    assert office.delivery_meals == "lunch" and office.delivers("lunch") and not walkin.delivers("lunch")
    day = date(2026, 10, 6)
    assert svc.serve(company=company, user=owner, member=office, meal="lunch", day=day).mode == "delivery"
    assert svc.serve(company=company, user=owner, member=office, meal="dinner", day=day).mode == "dine_in"
    assert svc.serve(company=company, user=owner, member=walkin, meal="lunch", day=day).mode == "dine_in"
    lunch = svc.today(company, day)["meals"][1]
    assert (lunch["delivery"], lunch["dine_in"]) == (1, 1)
    rows = svc.delivery_list(company, "lunch", day)
    assert [(r["m"], r["address"], r["done"]) for r in rows] == [(office, "Al Noor Trading, 3rd floor", True)]
    assert svc.delivery_list(company, "nonsense", day) == []


def test_mess_extras_menu_and_delivery_pages():
    from apps.industry.models import MessExtra, MessExtraItem, MessMenu
    from django.utils import timezone
    company, client, owner = _signup("restaurant", "m10@t.qa")
    other, _c2, _o2 = _signup("restaurant", "m11@t.qa")
    foreign = MessExtraItem.objects.create(company=other, name="Theirs", price=Decimal("1"))
    plan = _plan(company)
    member = svc.join(company=company, user=owner, plan=plan, bill_now=False, start_date=timezone.localdate(),
                      customer=Customer.objects.create(company=company, name="Nizar", phone="+97455512345"))

    client.post(reverse("webapp:mess_extras"), {"name": "Egg", "price": "1.50"})
    assert client.post(reverse("webapp:mess_extras"), {"name": "egg", "price": "2"}).status_code == 200  # duplicate
    egg = MessExtraItem.objects.get(company=company)
    client.post(reverse("webapp:mess_home"), {"action": "extra", "member": member.id, "item": egg.id})
    client.post(reverse("webapp:mess_home"), {"action": "extra", "member": member.id, "item": foreign.id})
    client.post(reverse("webapp:mess_member", args=[member.id]), {"action": "extra", "name": "Mutton", "price": "9", "quantity": "2"})
    assert sorted(MessExtra.objects.filter(member=member).values_list("name", "unit_price")) == [
        ("Egg", Decimal("1.50")), ("Mutton", Decimal("9.00"))]
    home = client.get(reverse("webapp:mess_home")).content.decode()
    assert "Egg" in home and "Theirs" not in home
    client.post(reverse("webapp:mess_member", args=[member.id]), {"action": "bill_extras"})
    assert not MessExtra.objects.filter(member=member, invoice__isnull=True).exists()

    weekday = timezone.localdate().weekday()
    client.post(reverse("webapp:mess_menu", args=[plan.id]), {f"m_{weekday}_lunch": "Ghee rice, chicken", "m_0_dinner": "Chapati"})
    assert MessMenu.objects.filter(plan=plan).count() >= 1
    page = client.get(reverse("webapp:mess_menu", args=[plan.id])).content.decode()
    assert "Ghee rice, chicken" in page and "wa.me/?text=" in page and "wa.me/97455512345" in page
    assert "Ghee rice, chicken" in client.get(reverse("webapp:mess_home")).content.decode()
    assert "Ghee rice, chicken" in client.get(reverse("webapp:mess_menu", args=[plan.id]) + "?print=1").content.decode()
    other_plan = _plan(other)
    assert client.get(reverse("webapp:mess_menu", args=[other_plan.id])).status_code == 404

    client.post(reverse("webapp:mess_member", args=[member.id]), {
        "action": "edit", "name": "Nizar", "phone": "+97455512345", "plan": plan.id, "monthly_fee": "", "notes": "",
        "delivery_meals": ["lunch", "dinner"], "delivery_address": "Villa 4, Al Waab"})
    member.refresh_from_db()
    assert member.delivery_meals == "lunch,dinner" and member.delivery_address == "Villa 4, Al Waab"
    page = client.get(reverse("webapp:mess_delivery") + "?meal=lunch").content.decode()
    assert "Villa 4, Al Waab" in page and "wa.me/?text=" in page
    client.post(reverse("webapp:mess_delivery"), {"meal": "lunch", "member": member.id})
    assert MessMeal.objects.get(member=member, meal="lunch").mode == "delivery"


def test_member_contact_numbers():
    from django.utils import timezone
    company, client, owner = _signup("restaurant", "m12@t.qa")
    plan = _plan(company)
    old = Customer.objects.create(company=company, name="Old customer")
    client.post(reverse("webapp:mess_join"), {"plan": plan.id, "customer": old.id, "new_customer_phone": "+974 5551 2233",
                                              "alt_phone": "4444 1111", "email": "old@example.qa",
                                              "start_date": timezone.localdate().isoformat()})
    member = MessMember.objects.get(customer=old)
    old.refresh_from_db()
    assert (old.phone, old.email, member.alt_phone) == ("+974 5551 2233", "old@example.qa", "4444 1111")

    page = client.post(reverse("webapp:mess_member", args=[member.id]), {
        "action": "edit", "name": "Old customer", "phone": "call me", "plan": plan.id})
    assert page.status_code == 200 and "Enter a valid phone number." in page.content.decode()
    client.post(reverse("webapp:mess_member", args=[member.id]), {
        "action": "edit", "name": "  Anwar   K ", "phone": "+974 6600 1122", "alt_phone": "", "email": "anwar@example.qa",
        "plan": plan.id, "monthly_fee": "", "notes": "Room 3"})
    member.refresh_from_db()
    member.customer.refresh_from_db()
    assert (member.customer.name, member.customer.phone, member.customer.email, member.alt_phone, member.notes) == (
        "Anwar K", "+974 6600 1122", "anwar@example.qa", "", "Room 3")
    page = client.get(reverse("webapp:mess_member", args=[member.id])).content.decode()
    assert "wa.me/97466001122" in page and 'href="tel:+974 6600 1122"' in page
    assert "+974 6600 1122" in client.get(reverse("webapp:mess_home") + "?q=6600").content.decode()
