"""Website kit: the platform admin connects a client's website; forms and feeds reach that client only."""
import io
import zipfile
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from apps.crm.models import Activity, Lead
from apps.industry import website_kit as svc
from apps.industry.models import BookableResource, CareersSite, OnlineBooking
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))


def _signup(code, email):
    client = Client(REMOTE_ADDR=f"10.8.0.{next(_ips)}")
    client.post(reverse("webapp:signup"), {
        "business_name": f"Biz {code}", "business_type": code, "country": "Qatar", "full_name": "Owner",
        "email": email, "phone": "+97455550000", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(email=email), client


@pytest.fixture
def admin_client():
    cache.clear()
    call_command("seed_platform")
    admin = get_user_model().objects.create_user(username="pa", email="pa@bp.qa", password="Pass-12345!", is_platform_admin=True)
    c = Client()
    c.force_login(admin)
    return c


def test_only_platform_admin_sees_the_kit(admin_client):
    salon, owner_client = _signup("saloon", "s@t.qa")
    assert owner_client.get(reverse("webapp:kit_list")).status_code == 302
    assert owner_client.get(reverse("webapp:kit_detail", args=[salon.id])).status_code == 302
    assert owner_client.get(reverse("webapp:kit_wp_plugin", args=[salon.id])).status_code == 302
    page = admin_client.get(reverse("webapp:kit_detail", args=[salon.id])).content.decode()
    assert "bookpilot_booking" in page and "bookpilot_enquiry" in page and "bookpilot_form]" not in page
    assert "Biz saloon" in admin_client.get(reverse("webapp:kit_list") + "?q=saloon").content.decode()


def test_feeds_per_business_type(admin_client):
    from apps.verticals.saloon.models import SaloonService
    salon, _c = _signup("saloon", "s1@t.qa")
    SaloonService.objects.create(company=salon, name="Haircut", duration_minutes=30, price=Decimal("40"))
    hotel, _c = _signup("hotel_apartment", "h1@t.qa")
    BookableResource.objects.create(company=hotel, name="Sea view suite", kind="room", rate=Decimal("650"), rate_unit="night")
    for company, kind, name in ((salon, "services", "Haircut"), (hotel, "resources", "Sea view suite")):
        kit = svc.kit_for(company)
        data = Client().get(reverse("webapp:kit_catalogue", args=[kit.public_id])).json()
        assert data["kind"] == kind and data["items"][0]["name"] == name
        info = Client().get(reverse("webapp:kit_info", args=[kit.public_id]))
        assert info["Access-Control-Allow-Origin"] == "*" and info.json()["name"] == company.name
        assert "booking_form_js" in info.json()["links"]
    assert "Haircut" not in str(Client().get(reverse("webapp:kit_catalogue", args=[svc.kit_for(hotel).public_id])).json())


def test_enquiry_becomes_a_crm_lead_for_that_client_only(admin_client):
    shop, owner_client = _signup("supermarket", "shop@t.qa")
    other, _c = _signup("supermarket", "other@t.qa")
    kit = svc.kit_for(shop)
    url = reverse("webapp:kit_enquiry", args=[kit.public_id])
    resp = Client().post(url, {"name": "Fatima", "phone": "+974 5512 0000", "subject": "Bulk order",
                               "message": "Do you deliver to Lusail?"}, HTTP_ORIGIN="https://www.shop.qa")
    assert resp.status_code == 201 and resp["Access-Control-Allow-Origin"] == "https://www.shop.qa"
    lead = Lead.objects.for_company(shop).get()
    assert lead.name == "Fatima" and lead.source == "Website · www.shop.qa"
    assert Activity.objects.for_company(shop).get(lead=lead).notes == "Do you deliver to Lusail?"
    assert not Lead.objects.for_company(other).exists()
    assert Client().post(url, {"name": "X"}).status_code == 400  # needs phone or email
    Client().post(url, {"name": "Bot", "phone": "+97455550001", "company_website": "spam"})
    assert not Lead.objects.for_company(shop).filter(name="Bot").exists()
    # JSON body from a server with the API key (no rate limit)
    for i in range(12):
        ok = Client().post(url, data=f'{{"name": "API {i}", "email": "a{i}@x.qa"}}', content_type="application/json",
                           HTTP_X_API_KEY=kit.api_key)
    assert ok.status_code == 201 and Lead.objects.for_company(shop).filter(name__startswith="API").count() == 12
    js = Client().get(reverse("webapp:kit_enquiry_js", args=[kit.public_id])).content.decode()
    assert "/enquiry/" in js and "{{" not in js


def test_connect_domain_test_and_server_keys(admin_client):
    agency, owner_client = _signup("recruitment_agency", "rec@t.qa")
    detail = reverse("webapp:kit_detail", args=[agency.id])
    admin_client.get(detail)
    kit = svc.kit_for(agency)
    careers = CareersSite.objects.get(company=agency)
    html = f'<html><div class="bookpilot-form"></div><script src="https://x/careers/{careers.slug}/form.js"></script></html>'
    with mock.patch("requests.get", return_value=mock.Mock(status_code=200, text=html)):
        admin_client.post(detail, {"action": "connect", "domain": "mite.socialdrive.qa", "page": "https://mite.socialdrive.qa/careers"})
    kit.refresh_from_db(); careers.refresh_from_db()
    assert "https://mite.socialdrive.qa" in kit.allowed_origins and kit.last_check_ok and kit.connected_at
    assert careers.allowed_origins == kit.allowed_origins
    with mock.patch("requests.get", return_value=mock.Mock(status_code=200, text="<html>nothing</html>")):
        admin_client.post(detail, {"action": "test"})
    kit.refresh_from_db()
    assert not kit.last_check_ok and "no BookPilot form" in kit.last_check
    # the client sees only the status, not the code
    page = owner_client.get(reverse("webapp:rec_website")).content.decode()
    assert "mite.socialdrive.qa" in page and "form.js" not in page
    # Python server posts an application with the kit key, even with the hosted page off
    resp = Client().post(reverse("webapp:careers_apply", args=[careers.slug]) + "?format=json",
                         {"name": "Ravi", "phone": "+91 98765 00000", "passport_no": "R1"}, HTTP_X_API_KEY=kit.api_key)
    assert resp.status_code == 201
    wrong = Client().post(reverse("webapp:careers_apply", args=[careers.slug]) + "?format=json",
                          {"name": "Bad", "phone": "+91 98765 00001", "passport_no": "B1"}, HTTP_X_API_KEY="nope")
    assert wrong.status_code == 404
    # downloads are pre-filled for this client
    z = zipfile.ZipFile(io.BytesIO(admin_client.get(reverse("webapp:kit_wp_plugin", args=[agency.id])).content))
    php = z.read("bookpilot-connect/bookpilot-connect.php").decode()
    assert f"'{kit.public_id}'" in php and f"'{careers.slug}'" in php and "add_shortcode('bookpilot_enquiry'" in php
    py = admin_client.get(reverse("webapp:kit_python_client", args=[agency.id])).content.decode()
    assert kit.api_key in py and "class BookPilot" in py and "{{" not in py
    admin_client.post(detail, {"action": "disconnect"})
    kit.refresh_from_db()
    assert kit.allowed_origins == ""


def test_booking_api_key_skips_rate_limit(admin_client):
    from datetime import timedelta
    from django.utils import timezone
    resto, _c = _signup("restaurant", "food@t.qa")
    from apps.industry import online_booking
    site = online_booking.site_for(resto)
    kit = svc.kit_for(resto)
    day = (timezone.localdate() + timedelta(days=3)).isoformat()
    for i in range(14):
        r = Client().post(reverse("webapp:book_submit", args=[site.slug]) + "?format=json",
                          {"date": day, "time": "20:00", "guests": 2, "name": f"G{i}", "phone": "+97455551111"},
                          HTTP_X_API_KEY=kit.api_key)
    assert r.status_code == 201 and OnlineBooking.objects.for_company(resto).count() == 14


@override_settings(RESTAURANT_STARTER_KIT=True)
def test_wordpress_menu_feed_has_sold_out_and_offers(admin_client):
    import datetime
    from django.utils import timezone
    from apps.sales.models import Promotion
    from apps.verticals.restaurant.models import RestaurantMenuItem
    company, _c = _signup("restaurant", "wp1@t.qa")
    RestaurantMenuItem.objects.for_company(company).filter(product__sku="KL-masala-dosa").update(is_available=False)
    today = timezone.localdate()
    Promotion.objects.create(company=company, name="Biryani Friday", discount_type="percentage", discount_value=15,
                             start_date=today, end_date=today + datetime.timedelta(days=3))
    kit = svc.kit_for(company)
    items = Client().get(reverse("webapp:kit_catalogue", args=[kit.public_id])).json()["items"]
    dosa = next(i for i in items if i["name"] == "Masala Dosa")
    assert dosa["available"] is False and dosa["vegetarian"] is True and dosa["category"] == "Breakfast"
    offers = Client().get(reverse("webapp:kit_offers", args=[kit.public_id])).json()
    assert offers["items"][0]["name"] == "Biryani Friday" and offers["items"][0]["discount"] == "15%"
    plugin = admin_client.get(reverse("webapp:kit_wp_plugin", args=[company.id]))
    php = zipfile.ZipFile(io.BytesIO(plugin.content)).read("bookpilot-connect/bookpilot-connect.php").decode()
    assert "add_shortcode('bookpilot_offers'" in php and "hide_sold_out" in php and "Version: 1.3.0" in php
