"""A recruitment agency gets its own short sidebar in work order (website last, no POS / stock / coupons) and
overview tiles that fit the work (no today's sales or low stock)."""
import re

import pytest
from django.urls import reverse

from .test_recruitment import agency  # noqa: F401

pytestmark = pytest.mark.django_db


def test_sidebar_in_work_order_and_overview_tiles(agency):
    html = agency["client"].get(reverse("webapp:dashboard")).content.decode()
    nav = html[html.index('<nav class="sidebar"'):html.index("</nav>")]
    sections = [s.split(" ", 1)[1] for s in re.findall(r"<summary>([^<]*)</summary>", nav)]
    assert sections == ["Recruitment", "Site workers", "Office staff", "Money", "More", "Settings", "Website"]
    assert reverse("webapp:rec_candidate_add") in nav and reverse("webapp:site_editor") in nav
    for retail in ("webapp:pos", "webapp:coupon_list", "webapp:loyalty_accounts_list", "webapp:stock_home"):
        assert f'href="{reverse(retail)}"' not in nav
    page = html[html.index("</nav>"):]
    assert "Interviews (next 7 days)" in page and "Documents expiring (30 days)" in page
    assert "Low stock items" not in page and "Today&#x27;s sales" not in page
    assert reverse("webapp:rec_job_add") in page and "🧾 New bill" not in page
