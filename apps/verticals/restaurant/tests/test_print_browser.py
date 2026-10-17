"""Printing in a real browser: the receipt / KOT page is loaded in a hidden frame and the print window opens.
(X-Frame-Options DENY on those pages made the browser refuse the frame, so nothing printed.)"""
import os
import shutil

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.verticals.restaurant.models import KitchenTicket, RestaurantOrder

from .test_online_orders import _item, _restaurant

pytestmark = pytest.mark.django_db(transaction=True)
CHROMIUM = "/opt/pw-browsers/chromium"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def test_print_pages_may_load_in_a_same_site_frame():
    company, owner, _kit = _restaurant("pf1@t.qa")
    owner.post(reverse("webapp:restaurant_order_add"), {"channel": "takeaway"})
    order = RestaurantOrder.objects.for_company(company).latest("id")
    receipt = owner.get(reverse("webapp:restaurant_receipt_print", args=[order.id]))
    assert receipt.status_code == 200 and receipt.headers.get("X-Frame-Options") == "SAMEORIGIN"
    page = owner.get(reverse("webapp:restaurant_order_detail", args=[order.id]))
    assert page.headers.get("X-Frame-Options") == "DENY"  # everything else still refuses frames


@pytest.mark.skipif(not (os.path.exists(CHROMIUM) or shutil.which("chromium")), reason="no browser")
def test_receipt_and_kot_print_in_chromium(live_server):
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    from playwright.sync_api import sync_playwright
    company, owner, _kit = _restaurant("pf2@t.qa")
    owner.post(reverse("webapp:restaurant_order_add"), {"channel": "takeaway"})
    order = RestaurantOrder.objects.for_company(company).latest("id")
    item = _item(company, "KL-thalassery-chicken-biryani")
    owner.post(reverse("webapp:restaurant_order_detail", args=[order.id]),
               {"action": "quick_add", "product_id": item.product_id, "quantity": 1})
    owner.post(reverse("webapp:restaurant_order_detail", args=[order.id]), {"action": "send_kitchen"})
    ticket = KitchenTicket.objects.filter(order=order).first()
    session = owner.cookies["sessionid"].value
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM if os.path.exists(CHROMIUM) else None)
        ctx = browser.new_context()
        ctx.add_cookies([{"name": "sessionid", "value": session, "url": live_server.url}])
        page = ctx.new_page()
        # count print() calls made inside any frame of the page
        page.add_init_script("window.__printed=[];window.print=function(){(window.top.__printed||[]).push(document.title)}")
        page.goto(live_server.url + reverse("webapp:restaurant_order_detail", args=[order.id]))
        page.evaluate("""async () => { await Devices.printReceipt({htmlUrl: PRINT.receiptHtml, dataUrl: PRINT.receiptData, drawer:false}); }""")
        page.wait_for_function("window.__printed.length >= 1", timeout=10000)
        printed = page.evaluate("window.__printed")
        assert order.order_number in printed[0]
        assert ticket is not None
        kot = reverse("webapp:restaurant_kot_print", args=[ticket.id])
        page.evaluate(f"async () => {{ await Devices.printKot({{htmlUrl: '{kot}', dataUrl: ''}}); }}")
        page.wait_for_function("window.__printed.length >= 2", timeout=10000)
        assert ticket.ticket_number in page.evaluate("window.__printed")[1]
        # the "Test print" button on the Devices page (browser printer)
        page.goto(live_server.url + reverse("webapp:devices"))
        page.evaluate("async () => { window.__printed=[]; await Devices.testPrint('receipt'); }")
        page.wait_for_function("window.__printed.length >= 1", timeout=10000)
        assert len(ctx.pages) == 1  # no blank tab opened
        # charts work without an outside CDN
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(live_server.url + reverse("webapp:analytics"))
        assert page.evaluate("typeof Chart") == "function" and not errors, errors
        browser.close()


def test_favicon_and_chart_library_are_served_locally(client):
    assert client.get("/favicon.ico").status_code == 301
    from django.contrib.staticfiles import finders
    assert finders.find("vendor/chart.umd.min.js") and finders.find("icons/favicon.ico")
