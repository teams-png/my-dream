"""Online booking form for every business type that takes bookings: requests reach only their own business,
staff confirm them into the real reservation / booking / appointment."""
import io
import zipfile
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.industry import online_booking as svc
from apps.industry.models import BookableResource, Booking, OnlineBooking
from apps.modules.catalog import BUSINESS_TYPE_MAP, online_booking_kind
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db
ORIGIN = "https://my-wordpress.example"


_ips = iter(range(1, 250))


def _signup(code, email):
    client = Client(REMOTE_ADDR=f"10.9.0.{next(_ips)}")  # signups are rate limited per IP
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email=email)
    return company, client


@pytest.fixture(autouse=True)
def platform(settings):
    cache.clear()
    call_command("seed_platform")


def _post(site, data):
    return Client().post(reverse("webapp:book_submit", args=[site.slug]) + "?format=json", data, HTTP_ORIGIN=ORIGIN)


def _day(n=3):
    return (timezone.localdate() + timedelta(days=n)).isoformat()


def test_every_booking_type_gets_a_working_form():
    kinds = {code: online_booking_kind(code) for code in BUSINESS_TYPE_MAP}
    assert kinds["saloon"] == "appointment" and kinds["dental_clinic"] == "appointment"
    assert kinds["hotel_apartment"] == "resource" and kinds["restaurant"] == "table" and kinds["catering_company"] == "event"
    assert kinds["supermarket"] is None
    for code in ("spa", "beauty_parlour", "gym", "vehicle_wash", "car_rental", "cafe_juice_shop", "medical_clinic"):
        company, client = _signup(code, f"{code}@t.qa")
        assert client.get(reverse("webapp:ob_settings")).status_code == 200, code
        site = svc.site_for(company)
        js = Client().get(reverse("webapp:book_form_js", args=[site.slug])).content.decode()
        assert '"kind": "%s"' % kinds[code] in js and "{{" not in js, code
        assert Client().get(reverse("webapp:book_page", args=[site.slug])).status_code == 200


def test_salon_request_confirm_opens_prefilled_appointment():
    from apps.verticals.saloon.models import SaloonService
    salon, client = _signup("saloon", "salon@t.qa")
    other, other_client = _signup("saloon", "salon2@t.qa")
    cut = SaloonService.objects.create(company=salon, name="Haircut", duration_minutes=30, price=Decimal("40"))
    site = svc.site_for(salon)
    assert "Haircut" in Client().get(reverse("webapp:book_options", args=[site.slug])).content.decode()
    resp = _post(site, {"item": cut.id, "date": _day(), "time": "10:30", "name": "Omar", "phone": "+974 5555 1111",
                        "notes": "Short on sides"})
    assert resp.status_code == 201 and resp["Access-Control-Allow-Origin"] == ORIGIN
    req = OnlineBooking.objects.for_company(salon).get()
    assert req.item_name == "Haircut" and req.kind == "appointment" and req.source == "my-wordpress.example"
    assert not OnlineBooking.objects.for_company(other).exists()
    assert "Omar" in client.get(reverse("webapp:dashboard")).content.decode()
    assert other_client.get(reverse("webapp:ob_detail", args=[req.id])).status_code == 404
    done = client.post(reverse("webapp:ob_detail", args=[req.id]), {"action": "confirm"})
    req.refresh_from_db()
    assert req.status == "confirmed" and req.customer.phone.startswith("+974")
    assert reverse("webapp:saloon_appointment_book") in done["Location"] and f"service={cut.id}" in done["Location"]
    form = client.get(done["Location"]).context["form"]
    assert str(form.initial["service"]) == str(cut.id) and str(form.initial["customer"]) == str(req.customer_id)
    # another business's id is not accepted as a service here
    _post(site, {"item": 999999, "date": _day(), "time": "11:00", "name": "X", "phone": "+97455552222"})
    assert OnlineBooking.objects.for_company(salon).filter(name="X").get().item_id is None


def test_hotel_request_becomes_a_booking_and_clashes_are_shown():
    hotel, client = _signup("hotel_apartment", "hotel@t.qa")
    room = BookableResource.objects.create(company=hotel, name="Room 101", kind="room", rate=Decimal("300"), rate_unit="night",
                                   capacity=2)
    assert _post(svc.site_for(hotel), {"item": room.id, "date": _day(5), "end_date": _day(7), "guests": 5, "name": "Big",
                                       "phone": "+97455550001"}).status_code == 400
    site = svc.site_for(hotel)
    bad = _post(site, {"item": room.id, "date": _day(5), "name": "Ann", "phone": "+97455553333"})
    assert bad.status_code == 400  # a night stay needs the check-out date
    _post(site, {"item": room.id, "date": _day(5), "end_date": _day(7), "guests": 2, "name": "Ann", "phone": "+97455553333"})
    _post(site, {"item": room.id, "date": _day(6), "end_date": _day(8), "guests": 1, "name": "Ben", "phone": "+97455554444"})
    ann, ben = OnlineBooking.objects.for_company(hotel).order_by("id")
    client.post(reverse("webapp:ob_detail", args=[ann.id]), {"action": "confirm", "resource": room.id})
    booking = Booking.objects.for_company(hotel).get()
    assert booking.resource == room and booking.guests == 2 and (booking.end - booking.start).days >= 1
    page = client.get(reverse("webapp:ob_detail", args=[ben.id])).content.decode()
    assert "Booked" in page  # Room 101 is taken for Ben's dates
    client.post(reverse("webapp:ob_detail", args=[ben.id]), {"action": "confirm", "resource": room.id})
    ben.refresh_from_db()
    assert ben.status == "new" and Booking.objects.for_company(hotel).count() == 1
    client.post(reverse("webapp:ob_detail", args=[ben.id]), {"action": "decline", "reason": "Fully booked"})
    ben.refresh_from_db()
    assert ben.status == "declined"
    assert "Fully%20booked" in client.get(reverse("webapp:ob_detail", args=[ben.id])).content.decode()


def test_restaurant_table_and_validation():
    from apps.verticals.restaurant.models import TableReservation
    resto, client = _signup("restaurant", "food@t.qa")
    site = svc.site_for(resto)
    assert _post(site, {"date": _day(), "guests": 4, "name": "Sara", "phone": "+97455556666"}).status_code == 400  # time needed
    past = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert _post(site, {"date": past, "time": "20:00", "name": "Sara", "phone": "+97455556666"}).status_code == 400
    assert _post(site, {"date": _day(), "time": "20:00", "guests": 4, "name": "Sara", "phone": "12"}).status_code == 400
    ok = _post(site, {"date": _day(), "time": "20:00", "guests": 4, "name": "Sara", "phone": "+97455556666", "notes": "Birthday"})
    assert ok.status_code == 201
    req = OnlineBooking.objects.for_company(resto).get()
    client.post(reverse("webapp:ob_detail", args=[req.id]), {"action": "confirm"})
    res = TableReservation.objects.for_company(resto).get()
    assert res.guest_count == 4 and res.customer_name == "Sara" and "Birthday" in res.notes
    # honeypot
    _post(site, {"date": _day(), "time": "20:00", "name": "Bot", "phone": "+97455557777", "company_website": "x"})
    assert not OnlineBooking.objects.for_company(resto).filter(name="Bot").exists()
    # switched off → not public
    site.enabled = False
    site.save()
    assert Client().get(reverse("webapp:book_page", args=[site.slug])).status_code == 404


def test_wordpress_plugin_and_retail_has_no_booking():
    salon, client = _signup("saloon", "wp@t.qa")
    site = svc.site_for(salon)
    assert client.get(reverse("webapp:ob_wp_plugin")).status_code == 302  # clients don't get the plugin
    owner = salon.memberships.first().user
    owner.is_platform_admin = True
    owner.save()
    z = zipfile.ZipFile(io.BytesIO(client.get(reverse("webapp:ob_wp_plugin")).content))
    php = z.read("bookpilot-booking-form/bookpilot-booking-form.php").decode()
    assert "add_shortcode('bookpilot_booking'" in php and f"/book/{site.slug}/form.js" in php and "bookpilot_form" not in php
    shop, shop_client = _signup("supermarket", "shop@t.qa")
    assert shop_client.get(reverse("webapp:ob_inbox")).status_code == 302


def test_website_form_and_plugin_are_owner_only():
    from django.contrib.auth import get_user_model
    from apps.tenants.models import CompanyMembership, Role
    for code, settings_url, plugin_url in (("saloon", "webapp:ob_settings", "webapp:ob_wp_plugin"),
                                           ("recruitment_agency", "webapp:rec_website", "webapp:rec_wp_plugin")):
        company, owner_client = _signup(code, f"own-{code}@t.qa")
        assert reverse(settings_url) in owner_client.get(reverse("webapp:dashboard")).content.decode()
        page = owner_client.get(reverse(settings_url)).content.decode()
        assert owner_client.get(reverse(settings_url)).status_code == 200 and "form.js" not in page  # no code for clients
        assert owner_client.get(reverse(plugin_url)).status_code == 302
        staff = get_user_model().objects.create_user(username=f"staff-{code}", email=f"staff-{code}@t.qa", password="Pass-12345!")
        CompanyMembership.objects.create(user=staff, company=company, role=Role.objects.get(company=company, name="Staff"))
        c = Client()
        c.force_login(staff)
        assert reverse(settings_url) not in c.get(reverse("webapp:dashboard")).content.decode()
        assert c.get(reverse(settings_url)).status_code == 403 and c.get(reverse(plugin_url)).status_code == 403
    # staff still handle the booking requests
    assert c.get(reverse("webapp:rec_home")).status_code == 200
