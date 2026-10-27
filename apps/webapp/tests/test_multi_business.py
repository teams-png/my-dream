"""One company running more than one business (a mobile shop that also sells computers and has a salon corner):
only a platform admin ticks the extra business types; each adds its menu and modules, nothing is repeated."""
import re

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _sections(html):
    nav = html[html.index('<nav class="sidebar"'):html.index("</nav>")]
    return nav, [s.strip() for s in re.findall(r"<summary>([^<]*)</summary>", nav)]


def test_platform_admin_ticks_extra_business_types(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Star Mobiles", "business_type": "mobile_shop", "country": "Qatar", "full_name": "Owner",
        "email": "owner@star.test", "phone": "", "password": "Gold-Shop-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="owner@star.test")
    nav, before = _sections(client.get(reverse("webapp:dashboard")).content.decode())
    assert "Mobile Shop" in before and reverse("webapp:saloon_appointment_list") not in nav

    # the owner cannot open the platform page; a platform admin ticks Home Appliances Store and Saloon
    url = reverse("webapp:platform_admin_manage_business_suites", args=[company.id])
    assert client.get(url).status_code in (302, 403)
    admin = User.objects.create_user(username="pa@bp.qa", email="pa@bp.qa", password="Pa-Pass-12345",
                                     is_platform_admin=True, is_superuser=True, is_staff=True)
    pa = Client()
    pa.force_login(admin)
    page = pa.get(url).content.decode()
    assert "Tick every business this client runs" in page and "Home Appliances Store" in page
    ids = [BusinessType.objects.get(code=c).id for c in ("home_appliances_store", "saloon")]
    assert pa.post(url, {"business_types": ids}).status_code == 302

    html = client.get(reverse("webapp:dashboard")).content.decode()
    nav, after = _sections(html)
    assert "Mobile Shop · Home Appliances Store · Saloon / Barber Shop" in html or (
        "Home Appliances Store" in nav and "Saloon" in nav)
    assert reverse("webapp:saloon_appointment_list") in nav            # the salon's own menu joins
    assert after.count("Mobile Shop") == 1 and "Home Appliances Store" not in after  # same products: no repeated section
    assert client.get(reverse("webapp:saloon_appointment_list")).status_code == 200
    assert '<details class="nav-section" >' in nav  # the extra suite's section starts folded to keep the menu short
    assert 'class="nav-link nav-bill' not in nav       # the overview has its own big New bill button
    assert 'class="nav-link nav-bill' in client.get(reverse("webapp:customer_list")).content.decode()

    # unticking removes the salon again
    pa.post(url, {"business_types": [ids[0]]})
    nav, _ = _sections(client.get(reverse("webapp:dashboard")).content.decode())
    assert reverse("webapp:saloon_appointment_list") not in nav


def test_extra_computer_shop_brings_its_service_desk_menu():
    """A shop with a service desk (computer shop: repairs and AMC) keeps its own section as an extra suite."""
    from apps.modules.catalog import SHOP_JOB_FEATURES, business_features
    assert SHOP_JOB_FEATURES & business_features("computer_shop")
