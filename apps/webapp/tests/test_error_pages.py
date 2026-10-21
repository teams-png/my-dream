"""Error pages are plain English + Arabic (no other languages), and the dark-mode button is in the top bar."""
import pytest
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name, english, arabic", [
    ("400.html", "Bad request", "طلب غير صالح"),
    ("403.html", "Access denied", "تم رفض الوصول"),
    ("403_csrf.html", "Page expired", "انتهت صلاحية الصفحة"),
    ("404.html", "Page not found", "الصفحة غير موجودة"),
    ("500.html", "Something went wrong", "حدث خطأ ما"),
])
def test_error_page_is_english_and_arabic(name, english, arabic):
    html = render_to_string(name)
    assert english in html and arabic in html and 'lang="ar"' in html
    assert "ക്ഷമിക്കണം" not in html  # no Malayalam or other languages


@override_settings(DEBUG=False)
def test_missing_page_uses_the_bilingual_404():
    response = Client().get("/no-such-page-here/")
    assert response.status_code == 404
    page = response.content.decode()
    assert "Page not found" in page and "الصفحة غير موجودة" in page


def test_dark_mode_button_in_top_bar(tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    top = page.split('class="topbar"')[1].split('class="am"')[0]
    assert "data-theme-toggle" in top and "dark.css" in page
