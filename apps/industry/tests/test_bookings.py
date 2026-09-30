from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.industry import bookings as svc
from apps.industry.models import BookableResource, Booking
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def at(days, hour=14):
    base = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime(base.year, base.month, base.day, hour, 0))


@pytest.fixture
def hotel(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Pearl Suites", "business_type": "hotel_apartment", "country": "Qatar", "full_name": "Hana Ali",
        "email": "h@pearl.test", "phone": "", "password": "Pearl-Suites-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="h@pearl.test")
    room = BookableResource.objects.create(company=company, name="Room 101", kind="room", rate=Decimal("250"),
                                           rate_unit="night", capacity=2)
    guest = Customer.objects.create(company=company, name="Guest One", phone="5551")
    user = company.memberships.first().user
    return {"company": company, "room": room, "guest": guest, "user": user, "client": client}


def test_billable_units():
    assert svc.billable_units("night", at(0), at(3, 12)) == 3
    assert svc.billable_units("night", at(0, 14), at(0, 20)) == 1
    assert svc.billable_units("day", at(0, 10), at(2, 10)) == 2
    assert svc.billable_units("day", at(0, 10), at(2, 10, ) + timedelta(minutes=20)) == 2  # grace period
    assert svc.billable_units("day", at(0, 10), at(2, 11)) == 3
    assert svc.billable_units("hour", at(0, 9), at(0, 11) + timedelta(minutes=45)) == 3
    assert svc.billable_units("event", at(0, 18), at(1, 2)) == 1


def test_no_double_booking(hotel):
    d = hotel
    svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                       start=at(1), end=at(4, 12))
    with pytest.raises(ValidationError):
        svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(3), end=at(5, 12))
    # back-to-back is fine: check-out at 12:00, next check-in at 14:00 the same day
    svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                       start=at(4), end=at(6, 12))
    with pytest.raises(ValidationError):
        svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(8), end=at(7))
    with pytest.raises(ValidationError):  # capacity
        svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(10), end=at(11), guests=5)


def test_cancelled_booking_frees_the_room(hotel):
    d = hotel
    b = svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(1), end=at(3, 12))
    svc.cancel(b)
    svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                       start=at(1), end=at(3, 12))


def test_check_out_creates_invoice_with_advance_and_extras(hotel):
    d = hotel
    b = svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(-3), end=at(0, 12), advance=Decimal("200"), advance_method="card")
    svc.check_in(b)
    b = svc.check_out(b, user=d["user"], extras=Decimal("40"), extras_note="Minibar", paid_now=Decimal("590"),
                      method="cash", when=at(0, 11))
    inv = b.invoice
    assert b.status == "completed" and b.number.startswith("BK-")
    assert inv.total == Decimal("790")  # 3 nights x 250 + 40
    assert inv.amount_paid == Decimal("790")
    with pytest.raises(ValidationError):
        svc.check_out(b, user=d["user"])


def test_late_return_is_charged(hotel):
    d = hotel
    car = BookableResource.objects.create(company=d["company"], name="Nissan Patrol", kind="vehicle", rate=Decimal("300"),
                                          rate_unit="day")
    b = svc.create_booking(company=d["company"], user=d["user"], resource=car, customer=d["guest"],
                           start=at(-2, 10), end=at(0, 10))
    svc.check_in(b)
    b = svc.check_out(b, user=d["user"], when=at(0, 15))  # 5 hours late -> 3 days
    assert b.invoice.total == Decimal("900")
    assert b.invoice.amount_paid == Decimal("0")  # balance stays on the customer's account


def test_overpayment_rejected(hotel):
    d = hotel
    b = svc.create_booking(company=d["company"], user=d["user"], resource=d["room"], customer=d["guest"],
                           start=at(-1), end=at(0, 12))
    with pytest.raises(ValidationError):
        svc.check_out(b, user=d["user"], paid_now=Decimal("9999"), when=at(0, 11))
    b.refresh_from_db()
    assert b.status == "reserved" and b.invoice is None


def test_pages_and_flow(hotel):
    d, c = hotel, hotel["client"]
    assert c.get(reverse("webapp:booking_board")).status_code == 200
    page = c.get(reverse("webapp:booking_board"))
    assert "Room 101" in page.content.decode()
    resp = c.post(reverse("webapp:booking_add"), {
        "resource": d["room"].id, "new_customer_name": "Walk In Family", "new_customer_phone": "5559",
        "start": at(2).strftime("%Y-%m-%dT%H:%M"), "end": at(4, 12).strftime("%Y-%m-%dT%H:%M"),
        "guests": 2, "advance": "100", "advance_method": "cash", "security_deposit": "0", "notes": ""})
    booking = Booking.objects.get(company=d["company"])
    assert resp.status_code == 302 and booking.customer.name == "Walk In Family"
    clash = c.post(reverse("webapp:booking_add"), {
        "resource": d["room"].id, "customer": d["guest"].id, "start": at(3).strftime("%Y-%m-%dT%H:%M"),
        "end": at(5, 12).strftime("%Y-%m-%dT%H:%M"), "guests": 1, "advance": "0", "advance_method": "cash",
        "security_deposit": "0"})
    assert clash.status_code == 200 and "already booked" in clash.content.decode()
    assert c.get(reverse("webapp:booking_detail", args=[booking.id])).status_code == 200
    c.post(reverse("webapp:booking_detail", args=[booking.id]), {"action": "check_in"})
    booking.refresh_from_db()
    assert booking.status == "checked_in"
    c.post(reverse("webapp:booking_detail", args=[booking.id]), {
        "action": "check_out", "extras": "0", "discount": "0", "paid_now": "400", "method": "cash"})
    booking.refresh_from_db()
    assert booking.status == "completed" and booking.invoice.total == Decimal("500")
    for name in ("booking_list", "booking_resources", "booking_resource_add"):
        assert c.get(reverse(f"webapp:{name}")).status_code == 200


def test_other_business_types_cannot_open_bookings(client, tenant_a, tenant_a_owner):
    client.force_login(tenant_a_owner)
    resp = client.get(reverse("webapp:booking_board"))
    assert resp.status_code == 302
