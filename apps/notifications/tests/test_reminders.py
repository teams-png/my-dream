from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.notifications import rules
from apps.notifications.daily import remind_due_soon, run_daily_jobs, run_for_company
from apps.notifications.models import DailyJobRun, Notification, NotificationDelivery
from apps.sales import services as sales

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice_due(tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="X", stock_price=Decimal("10"))
    today = date.today()
    inv = sales.create_invoice(company=tenant_a, user=tenant_a_owner, customer=base["customer"], date=today,
                               due_date=today + timedelta(days=5), warehouse=base["warehouse"],
                               lines=[{"product": base["product"], "quantity": 1, "unit_price": Decimal("50")}])
    return inv


def test_due_soon_uses_company_days_and_fires_once_per_step(tenant_a, invoice_due):
    today = date.today()
    assert remind_due_soon(tenant_a, today) == 0  # default 3 and 0 days: 5 days left is too early
    rules.save_rules(tenant_a, "customer_payment_due", [7, 1], True)
    assert remind_due_soon(tenant_a, today) == 1
    assert remind_due_soon(tenant_a, today) == 0  # same step: no repeat
    assert remind_due_soon(tenant_a, today + timedelta(days=4)) == 1  # 1 day left: next step
    assert Notification.objects.filter(company=tenant_a, notif_type="customer_payment_due").count() == 2


def test_email_switch_off_stops_email_deliveries(tenant_a, tenant_a_owner, invoice_due):
    tenant_a_owner.email = "owner@test.qa"
    tenant_a_owner.save()
    rules.save_rules(tenant_a, "customer_payment_due", [7], False)
    remind_due_soon(tenant_a)
    assert Notification.objects.filter(company=tenant_a, notif_type="customer_payment_due").exists()
    assert not NotificationDelivery.objects.filter(company=tenant_a).exists()


def test_threshold_helper():
    assert rules.threshold_for(5, [15, 7, 1]) == 7
    assert rules.threshold_for(0, [15, 7, 1]) == 1
    assert rules.threshold_for(20, [15, 7, 1]) is None


def test_daily_jobs_run_once_per_day_and_cron_needs_secret(client, settings, tenant_a, invoice_due):
    first = run_daily_jobs()
    assert first["companies"] >= 1 and DailyJobRun.objects.count() == 1
    assert run_daily_jobs() == {"skipped": "already ran today"}
    assert "companies" in run_daily_jobs(force=True)
    settings.CRON_SECRET = "s3cret"
    assert client.post(reverse("webapp:cron_daily")).status_code == 403
    assert client.post(reverse("webapp:cron_daily"), HTTP_X_CRON_KEY="wrong").status_code == 403
    ok = client.post(reverse("webapp:cron_daily") + "?force=1", HTTP_X_CRON_KEY="s3cret")
    assert ok.status_code == 200 and "companies" in ok.json()
    settings.CRON_SECRET = ""
    assert client.post(reverse("webapp:cron_daily"), HTTP_X_CRON_KEY="").status_code == 403


def test_settings_page_saves_rules_and_runs_checks(client, tenant_a, tenant_a_owner):
    client.force_login(tenant_a_owner)
    assert client.get(reverse("webapp:reminder_settings")).status_code == 200
    data = {f"email_{k}": "on" for k in rules.RULE_TYPES}
    data.update({"days_product_expiry": "60, 15,x, 1", "days_customer_payment_due": ""})
    data.pop("email_low_stock")
    client.post(reverse("webapp:reminder_settings"), data)
    assert rules.thresholds(tenant_a, "product_expiry") == [60, 15, 1]
    assert rules.thresholds(tenant_a, "customer_payment_due") == [0]
    assert not rules.email_enabled(tenant_a, "low_stock") and rules.email_enabled(tenant_a, "invoice_overdue")
    response = client.post(reverse("webapp:reminder_settings"), {"action": "run"})
    assert response.status_code == 302
    assert isinstance(run_for_company(tenant_a), dict)
