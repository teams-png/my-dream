"""The customer user guide (/guide/) and the Terms, Privacy and Refund pages.

The guide is plain HTML built by docs/user-guide/build.py into ./guide_site. Contact
details are filled in here from settings, so they can change without rebuilding it.
"""
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation

GUIDE_DIR = Path(__file__).resolve().parent / "guide_site"
GUIDE_LANGS = ("en", "ml", "ar")
NO_EMAIL = re.compile(r'<br>[^<>]*(?:<b>[^<>]*</b>)?\s*<a href="mailto:__SUPPORT_EMAIL__">__SUPPORT_EMAIL__</a>')
PAGE = re.compile(r"^(?:(?:en|ml|ar)/)?[a-z0-9-]+\.html$")


@lru_cache(maxsize=None)
def _read(path):
    return (GUIDE_DIR / path).read_text(encoding="utf-8")


def support_details():
    digits = re.sub(r"\D", "", settings.SUPPORT_WHATSAPP or "")
    return {
        "company": settings.LEGAL_COMPANY_NAME,
        "address": settings.LEGAL_COMPANY_ADDRESS,
        "cr_number": settings.LEGAL_CR_NUMBER,
        "country": settings.LEGAL_COUNTRY,
        "email": settings.SUPPORT_EMAIL,
        "whatsapp": settings.SUPPORT_WHATSAPP,
        "whatsapp_link": f"https://wa.me/{digits}" if digits else "",
        "phone_link": f"tel:+{digits}" if digits else "",
        "updated": settings.LEGAL_UPDATED,
    }


def _fill(html):
    s = support_details()
    number = escape(s["whatsapp"] or "—")
    if s["whatsapp_link"]:
        number = f'<a href="{s["whatsapp_link"]}" target="_blank" rel="noopener">{number}</a>'
    if not s["email"]:  # no address set: drop the "Email:" line rather than show it empty
        html = NO_EMAIL.sub("", html)
    return (html.replace("__SUPPORT_WHATSAPP__", number)
                .replace("__SUPPORT_EMAIL__", escape(s["email"] or ""))
                .replace("__COMPANY__", escape(s["company"] or "BookPilot")))


def guide_home(request):
    """Open the guide in the visitor's language when we have it."""
    lang = (translation.get_language() or "en").split("-")[0]
    return redirect(f"/guide/{lang if lang in GUIDE_LANGS else 'en'}/index.html")


def guide_page(request, path):
    if path == "style.css":
        response = HttpResponse(_read("style.css"), content_type="text/css; charset=utf-8")
    elif PAGE.match(path) and (GUIDE_DIR / path).is_file():
        response = HttpResponse(_fill(_read(path)), content_type="text/html; charset=utf-8")
    else:
        raise Http404("No such guide page.")
    response["Cache-Control"] = "public, max-age=600"
    return response


def guide_lang_home(request, lang):
    if lang not in GUIDE_LANGS:
        raise Http404
    return redirect(f"/guide/{lang}/index.html")


def legal_page(request, page):
    return render(request, f"webapp/public/legal_{page}.html", {"page": page, "legal": support_details()})
