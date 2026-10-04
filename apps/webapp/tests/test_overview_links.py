"""Every overview tile is a link, and every link opens a real page for that business type."""
import re

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings

from apps.modules.catalog import BUSINESS_TYPE_MAP

pytestmark = pytest.mark.django_db
TAG = re.compile(r'<a\b[^>]*>')
HOMES = {"restaurant": ["/restaurant/"], "hotel_apartment": ["/bookings/"], "school_training_institute": ["/education/"],
         "property_management": ["/property/"], "recruitment_agency": ["/recruitment/"]}


def _check(client, page, code, failures):
    html = client.get(page).content.decode()
    links = set()
    for tag in TAG.findall(html):
        if "stat-link" in tag or "r-stat" in tag:
            links.add(re.search(r'href="([^"]+)"', tag).group(1).replace("&amp;", "&"))
    for href in links:
        if href.startswith("#"):
            continue
        response = client.get(href)
        if response.status_code != 200:
            failures.append((code, page, href, response.status_code, response.get("Location", "")))
    return links


@override_settings(SIGNUP_LIMIT_PER_IP_PER_HOUR=100000)
def test_overview_tiles_open_their_details_for_every_business_type():
    cache.clear()
    call_command("seed_platform")
    failures, counted = [], 0
    for i, code in enumerate(sorted(BUSINESS_TYPE_MAP)):
        c = Client()
        c.post("/signup/", {"business_name": f"Tiles {code}", "business_type": code, "country": "Qatar",
                            "full_name": "Owner", "email": f"t{i}@tiles.test", "phone": "", "password": "Tile-Pass-2026!",
                            "accept_terms": "on", "website": ""})
        c.post("/setup/business/", {"skip_all": "1"})
        links = _check(c, "/", code, failures)
        assert len(links) >= 5, (code, links)  # 4 money tiles + business tiles + customers
        counted += len(links)
        for page in HOMES.get(code, []) + ["/finance/"]:
            found = _check(c, page, code, failures)
            if page == "/restaurant/":
                assert len(found) == 4, found
    assert not failures, failures[:20]
    assert counted > 500
