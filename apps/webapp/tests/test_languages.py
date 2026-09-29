import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("lang,text,direction", [
    ("ar", "تسجيل الدخول", 'dir="rtl"'),
    ("ml", "ലോഗിൻ", 'dir="ltr"'),
    ("en", "Sign in", 'dir="ltr"'),
])
def test_login_page_in_each_language(client, lang, text, direction):
    client.cookies["django_language"] = lang
    page = client.get(reverse("webapp:login")).content.decode()
    assert text in page and direction in page


def test_switch_language_and_numbers_keep_dot(client):
    resp = client.post("/i18n/setlang/", {"language": "ar", "next": "/login/"})
    assert resp.status_code == 302
    from django.template import Context, Template
    from django.utils import translation
    with translation.override("ar"):
        assert Template("{{ v|floatformat:2 }}").render(Context({"v": 1234.5})) == "1234.50"
