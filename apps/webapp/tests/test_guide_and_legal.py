"""The customer user guide (/guide/) and the Terms, Privacy and Refund pages."""
import filecmp
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.subscriptions.middleware import WEBAPP_ALLOWED_PREFIXES
from apps.webapp import guide_views

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.django_db


def test_guide_opens_in_the_visitors_language():
    assert Client().get("/guide/")["Location"] == "/guide/en/index.html"
    c = Client()
    c.cookies["django_language"] = "ml"
    assert c.get("/guide/")["Location"] == "/guide/ml/index.html"
    c.cookies["django_language"] = "hi"  # no Hindi guide yet -> English
    assert c.get("/guide/")["Location"] == "/guide/en/index.html"
    assert Client().get("/guide/ar/")["Location"] == "/guide/ar/index.html"


@override_settings(SUPPORT_WHATSAPP="+974 5555 0000", SUPPORT_EMAIL="help@example.qa", LEGAL_COMPANY_NAME="Test Co")
def test_guide_pages_are_served_with_the_support_details():
    page = Client().get("/guide/en/help.html")
    html = page.content.decode()
    assert page.status_code == 200 and page["Content-Type"].startswith("text/html")
    assert "+974 5555 0000" in html and "help@example.qa" in html and "Test Co" in html
    assert "__SUPPORT_" not in html and "__COMPANY__" not in html
    assert Client().get("/guide/style.css")["Content-Type"].startswith("text/css")
    for slug in ("restaurant", "bookings", "education", "property", "jewellery", "sell-by-weight", "recruitment",
                 "quotes-orders", "stock", "finance", "staff-hr", "website-online", "security-settings"):
        assert Client().get(f"/guide/en/guide-{slug}.html").status_code == 200, slug
    ml = Client().get("/guide/ml/guide-restaurant.html").content.decode()
    assert "ടേബിളുകൾ" in ml and 'href="/terms/"' in ml


def test_guide_rejects_anything_that_is_not_a_page():
    for path in ("/guide/en/nope.html", "/guide/../settings.py", "/guide/en/../../urls.py", "/guide/en/index.htm",
                 "/guide/xx/index.html", "/guide/xx/"):
        assert Client().get(path).status_code == 404, path


def test_built_guide_matches_its_source(tmp_path):
    """docs/user-guide is the source; apps/webapp/guide_site must be rebuilt and committed with it."""
    env = {**os.environ, "GUIDE_OUT": str(tmp_path / "site")}
    subprocess.run([sys.executable, str(ROOT / "docs" / "user-guide" / "build.py")], check=True, env=env, capture_output=True)
    cmp = filecmp.dircmp(tmp_path / "site", guide_views.GUIDE_DIR)

    def differences(d):
        out = d.left_only + d.right_only + d.diff_files
        for sub in d.subdirs.values():
            out += differences(sub)
        return out
    assert differences(cmp) == [], "Run: python3 docs/user-guide/build.py"


@override_settings(LEGAL_COMPANY_NAME="Ajwaaz Trading", LEGAL_CR_NUMBER="12345", SUPPORT_EMAIL="hello@example.qa")
def test_terms_privacy_and_refund_pages():
    for name, words in (("terms", "Terms of Service"), ("privacy", "Privacy Policy"), ("refund_policy", "Refund")):
        r = Client().get(reverse(f"webapp:{name}"))
        html = r.content.decode()
        assert r.status_code == 200 and words in html, name
        assert "Ajwaaz Trading" in html and "12345" in html and "hello@example.qa" in html
    assert "7 days" in Client().get(reverse("webapp:refund_policy")).content.decode()


def test_website_and_sign_up_link_the_guide_and_policies():
    landing = Client().get(reverse("webapp:landing")).content.decode()
    for url in ("/guide/", "/terms/", "/privacy/", "/refund-policy/"):
        assert f'href="{url}"' in landing, url
    signup = Client().get(reverse("webapp:signup")).content.decode()
    assert 'href="/terms/"' in signup and 'href="/privacy/"' in signup and 'href="/refund-policy/"' in signup


def test_expired_accounts_can_still_read_the_guide_and_policies():
    for prefix in ("/guide", "/terms", "/privacy", "/refund-policy"):
        assert prefix in WEBAPP_ALLOWED_PREFIXES
