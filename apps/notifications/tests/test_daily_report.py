from datetime import date, datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounting.services import seed_chart_of_accounts
from apps.notifications import daily_report as dr
from apps.notifications.daily import run_for_company
from apps.notifications.models import DailyReportSettings, Notification
from apps.sales import services as sales

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    tenant_a_owner.email = "boss@test.qa"
    tenant_a_owner.save()
    base = sales_fixtures_factory(tenant_a, sku="JUICE", stock_price=Decimal("10"))
    inv = sales.create_invoice(company=tenant_a, user=tenant_a_owner, customer=base["customer"], date=date.today(),
                               warehouse=base["warehouse"], lines=[{"product": base["product"], "quantity": 3, "unit_price": Decimal("10")}])
    sales.record_customer_payment(company=tenant_a, user=tenant_a_owner, customer=base["customer"], amount=Decimal("20"),
                                  date=date.today(), invoice=inv)
    return {"company": tenant_a, "user": tenant_a_owner}


def test_summary_figures_and_text(shop):
    s = dr.build_summary(shop["company"], date.today())
    assert s["sales"] == Decimal("30") and s["bills"] == 1 and s["received"] == Decimal("20")
    assert s["receivable"] == Decimal("10") and s["top"][0]["product__name"].startswith("Product")
    assert "Sales:" in dr.summary_text(s)


def test_sent_once_a_day_by_email_and_in_app(shop, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    company = shop["company"]
    DailyReportSettings.load(company)
    DailyReportSettings.objects.filter(company=company).update(emails="acct@test.qa, bad-address")
    assert dr.send_daily_report(company, day=date.today()) == 2
    assert dr.send_daily_report(company, day=date.today()) == "skipped"
    assert len(mail.outbox) == 1 and set(mail.outbox[0].to) == {"boss@test.qa", "acct@test.qa"}
    assert Notification.objects.filter(company=company, title__startswith="Daily report").count() == 1
    DailyReportSettings.objects.filter(company=company).update(enabled=False, last_sent_on=None)
    assert run_for_company(company)["daily_owner_report"] == "skipped"


def test_report_day_after_midnight_is_yesterday():
    tz = timezone.get_current_timezone()
    assert dr.report_day(timezone.make_aware(datetime(2026, 9, 30, 1, 0), tz)) == date(2026, 9, 29)
    assert dr.report_day(timezone.make_aware(datetime(2026, 9, 30, 23, 0), tz)) == date(2026, 9, 30)


def test_page_settings_and_send(client, shop, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client.force_login(shop["user"])
    page = client.get(reverse("webapp:daily_report"))
    assert page.status_code == 200 and "wa.me/" in page.context["whatsapp"]
    client.post(reverse("webapp:daily_report"), {"enabled": "on", "emails": "x@test.qa", "whatsapp": "+974 5555 1234"})
    prefs = DailyReportSettings.objects.get(company=shop["company"])
    assert prefs.whatsapp_number == "+974 5555 1234" and "wa.me/97455551234" in client.get(reverse("webapp:daily_report")).context["whatsapp"]
    client.post(reverse("webapp:daily_report"), {"action": "send"})
    assert len(mail.outbox) == 1
