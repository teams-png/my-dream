"""Hosted business website: platform admin switches it on and sets the own domain; the owner designs it;
menu / services and offers come live from BookPilot."""
import datetime
import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Lead
from apps.industry import site_builder
from apps.industry import website_kit
from apps.industry.models import SiteDesign
from apps.sales.models import Promotion
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db
_ips = iter(range(1, 250))


def _signup(code, email):
    client = Client(REMOTE_ADDR=f"10.9.0.{next(_ips)}")
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


def _admin_save(admin_client, company, **extra):
    data = {"action": "admin", "a-enabled": "on", "a-custom_domain": "", "a-domain_status": "", "a-custom_css": "",
            "a-custom_html": ""}
    data.update(extra)
    return admin_client.post(reverse("webapp:site_admin_editor", args=[company.id]), data)


def _design_data(**extra):
    data = {"action": "design", "d-published": "on", "d-theme": "elegant", "d-font": "Poppins",
            "d-primary_color": "#123456", "d-accent_color": "#abcdef", "d-hero_title": "Best cuts in Doha",
            "d-hero_subtitle": "", "d-about": "Since 2015", "d-opening_hours": "Daily 10am–10pm", "d-whatsapp": "",
            "d-instagram": "@biz", "d-facebook": "", "d-tiktok": "", "d-map_url": "",
            "d-show_catalogue": "on", "d-show_offers": "on", "d-show_booking": "on", "d-show_contact": "on"}
    data.update(extra)
    return data


def test_owner_designs_after_admin_switches_it_on(admin_client):
    from apps.verticals.saloon.models import SaloonService
    salon, owner = _signup("saloon", "s@t.qa")
    SaloonService.objects.create(company=salon, name="Haircut", duration_minutes=30, price=Decimal("40"))
    today = timezone.localdate()
    Promotion.objects.create(company=salon, name="Eid special", discount_type="percentage", discount_value=Decimal("25"),
                             start_date=today, end_date=today + datetime.timedelta(days=5))
    page = owner.get(reverse("webapp:site_editor")).content.decode()
    assert "Website add-on" in page and 'name="d-theme"' not in page
    owner.post(reverse("webapp:site_editor"), _design_data())
    assert not SiteDesign.objects.get(company=salon).published  # add-on still off

    _admin_save(admin_client, salon)
    owner.post(reverse("webapp:site_editor"), _design_data())
    design = SiteDesign.objects.get(company=salon)
    assert design.published and design.theme == "elegant" and design.primary_color == "#123456"

    kit = website_kit.kit_for(salon)
    html = Client().get(reverse("webapp:site_public", args=[kit.public_id])).content.decode()
    assert "Best cuts in Doha" in html and "Haircut" in html and "25% off" in html and "Eid special" in html
    assert "instagram.com/biz" in html and "bookpilot-booking" in html and "bookpilot-enquiry" in html

    # a price change in BookPilot shows straight away
    SaloonService.objects.filter(company=salon).update(price=Decimal("55"))
    assert "55" in Client().get(reverse("webapp:site_public", args=[kit.public_id])).content.decode()


def test_unpublished_site_is_private_and_staff_cannot_edit(admin_client):
    salon, owner = _signup("saloon", "s2@t.qa")
    _admin_save(admin_client, salon)
    kit = website_kit.kit_for(salon)
    url = reverse("webapp:site_public", args=[kit.public_id])
    assert Client().get(url).status_code == 404
    assert owner.get(url + "?preview=1").status_code == 200
    assert Client().get(url + "?preview=1").status_code == 404
    from apps.tenants.models import CompanyMembership, Role
    staff = get_user_model().objects.create_user(username="st", email="st@t.qa", password="Pass-12345!")
    CompanyMembership.objects.create(company=salon, user=staff, role=Role.objects.get(company=salon, name="Staff"))
    c = Client()
    c.force_login(staff)
    assert c.get(reverse("webapp:site_editor")).status_code == 403
    # owners never see the admin-only fields
    assert 'name="a-custom_domain"' not in owner.get(reverse("webapp:site_editor")).content.decode()


def test_own_domain_serves_only_the_website(admin_client):
    salon, owner = _signup("saloon", "s3@t.qa")
    _admin_save(admin_client, salon, **{"a-custom_domain": "https://www.glow.qa/", "a-domain_status": "live"})
    owner.post(reverse("webapp:site_editor"), _design_data())
    design = SiteDesign.objects.get(company=salon)
    assert design.custom_domain == "www.glow.qa"
    assert "https://glow.qa" in website_kit.kit_for(salon).allowed_origins
    for host in ("www.glow.qa", "glow.qa"):
        response = Client(HTTP_HOST=host).get("/")
        assert response.status_code == 200 and "Best cuts in Doha" in response.content.decode()
    assert Client(HTTP_HOST="glow.qa").get("/login/").status_code == 404
    assert Client(HTTP_HOST="glow.qa").get(f"/kit/{website_kit.kit_for(salon).public_id}/enquiry.js").status_code == 200
    response = Client(HTTP_HOST="glow.qa").post(f"/kit/{website_kit.kit_for(salon).public_id}/enquiry/",
                                                {"name": "Noor", "phone": "55512345"}, HTTP_ORIGIN="https://glow.qa")
    assert response.status_code == 201 and Lead.objects.filter(company=salon, name="Noor").exists()

    # the same domain can't be given to a second client
    other, _ = _signup("spa", "sp@t.qa")
    _admin_save(admin_client, other, **{"a-custom_domain": "glow.qa"})
    assert not SiteDesign.objects.get(company=other).custom_domain

    # switching the domain off stops serving it
    _admin_save(admin_client, salon, **{"a-custom_domain": "", "a-domain_status": ""})
    assert site_builder.design_for_host("glow.qa") is None


def test_owner_cannot_reach_admin_builder(admin_client):
    salon, owner = _signup("saloon", "s4@t.qa")
    assert owner.get(reverse("webapp:site_admin_editor", args=[salon.id])).status_code == 302
    assert admin_client.get(reverse("webapp:site_admin_editor", args=[salon.id])).status_code == 200


def test_website_language_and_visitor_switch():
    cache.clear()
    company, _c = _signup("restaurant", "lang@t.qa")
    design = site_builder.design_for(company)
    design.enabled = design.published = True
    design.language, design.extra_languages = "ar", "ml,en,xx"
    design.save()
    kit = website_kit.kit_for(company)
    url = reverse("webapp:site_public", args=[kit.public_id])
    page = Client().get(url).content.decode()
    assert 'lang="ar" dir="rtl"' in page and "اتصل بنا" in page and "?lang=ml" in page and "?lang=xx" not in page
    ml = Client().get(url + "?lang=ml").content.decode()
    assert 'lang="ml" dir="ltr"' in ml and "ഞങ്ങളെ ബന്ധപ്പെടുക" in ml
    assert 'lang="ar"' in Client().get(url + "?lang=fr").content.decode()  # not offered → main language
    cart = Client().get(reverse("webapp:kit_order_js", args=[kit.public_id]) + "?lang=ml").content.decode()
    assert json.dumps("ഓർഡർ ചെയ്യുക")[1:-1] in cart and '"rtl": false' in cart
    enquiry = Client().get(reverse("webapp:kit_enquiry_js", args=[kit.public_id])).content.decode()
    assert json.dumps("راسلنا")[1:-1] in enquiry and '"rtl": true' in enquiry  # main language when the page asks for none
    feed = Client().get(reverse("webapp:kit_catalogue", args=[kit.public_id]) + "?lang=ar").json()
    assert feed["labels"]["sold_out"] and feed["labels"]["add"] == "+ إضافة"
