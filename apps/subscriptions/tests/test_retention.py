"""Unpaid trials: warnings, closing, deleting for good — and the accounts that must never be touched."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.inventory.services import record_stock_movement
from apps.notifications.models import Notification
from apps.sales import pos
from apps.subscriptions import retention
from apps.subscriptions.models import AccountRetention, DeletedAccountLog, Subscription, SubscriptionPayment
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _end_trial(company, days_ago):
    sub = Subscription.objects.get(company=company)
    sub.status = "expired"
    sub.trial_ends_at = sub.end_date = timezone.localdate() - timedelta(days=days_ago)
    sub.save()
    return sub


def test_ended_trial_gets_a_date_and_warnings_once(tenant_a, settings):
    settings.TRIAL_DELETE_AFTER_DAYS = 30
    sub = _end_trial(tenant_a, 16)  # 14 days left
    assert retention.delete_on(sub) == timezone.localdate() + timedelta(days=14)
    mail.outbox.clear()
    assert retention.run_daily()["warned"] == 1
    assert retention.run_daily()["warned"] == 0  # once per step
    assert Notification.objects.filter(company=tenant_a, title__contains="will be deleted").count() == 1
    assert len(mail.outbox) == 1 and "/billing/" in mail.outbox[0].body and "/account/export" in mail.outbox[0].body
    _end_trial(tenant_a, 20)  # 10 days left: no step today
    assert retention.run_daily()["warned"] == 0


def test_running_trial_paid_kept_and_demo_are_never_touched(tenant_a, tenant_b):
    sub = Subscription.objects.get(company=tenant_a)
    assert retention.delete_on(sub) is None  # trial still running
    sub = _end_trial(tenant_a, 90)
    SubscriptionPayment.objects.create(subscription=sub, amount=Decimal("399"), paid_on=timezone.localdate())
    assert retention.delete_on(sub) is None
    other = _end_trial(tenant_b, 90)
    AccountRetention.objects.create(company=tenant_b, keep=True)
    assert retention.delete_on(other) is None
    AccountRetention.objects.filter(company=tenant_b).update(keep=False)
    Company.objects.filter(pk=tenant_b.pk).update(is_demo=True)
    other.company.refresh_from_db()
    assert retention.delete_on(other) is None
    assert retention.run_daily() == {"warned": 0, "closed": 0, "deleted": 0}
    assert Company._base_manager.filter(pk__in=[tenant_a.pk, tenant_b.pk], is_active=True).count() == 2


def test_close_then_delete_everything(tenant_a, tenant_a_owner, tenant_b, sales_fixtures_factory, settings):
    settings.TRIAL_DELETE_AFTER_DAYS, settings.TRIAL_PURGE_GRACE_DAYS = 30, 7
    data = sales_fixtures_factory(tenant_a)
    record_stock_movement(company=tenant_a, product=data["product"], warehouse=data["warehouse"],
                          quantity=Decimal("5"), reason="adjustment", reference="opening")
    pos.checkout(company=tenant_a, user=tenant_a_owner, payload={
        "client_id": str(uuid.uuid4()), "payment_method": "cash", "total": "100.00",
        "created_at": timezone.now().isoformat(),
        "lines": [{"product_id": data["product"].id, "quantity": 1, "unit_price": "100.00", "name": "Thing"}]})
    _end_trial(tenant_a, 31)

    assert retention.run_daily()["closed"] == 1
    tenant_a.refresh_from_db()
    kept = AccountRetention.objects.get(company=tenant_a)
    assert not tenant_a.is_active and kept.purge_on == timezone.localdate() + timedelta(days=7)
    assert retention.run_daily()["deleted"] == 0  # still in the grace days

    AccountRetention.objects.filter(pk=kept.pk).update(purge_on=timezone.localdate())
    owner_email = tenant_a_owner.email
    assert retention.run_daily()["deleted"] == 1
    assert not Company._base_manager.filter(pk=tenant_a.pk).exists()
    assert not get_user_model().objects.filter(email=owner_email).exists()
    entry = DeletedAccountLog.objects.get()
    assert entry.company_name == "ABC Textile" and entry.owner_email == owner_email
    assert Company._base_manager.filter(pk=tenant_b.pk, is_active=True).exists()  # the neighbour is untouched


def test_owner_with_another_business_keeps_their_login(tenant_a, tenant_a_owner, company_factory):
    company_factory("Second Shop", "second-shop", owner=tenant_a_owner)
    assert retention.purge(tenant_a)
    assert get_user_model().objects.filter(pk=tenant_a_owner.pk).exists()


def test_platform_admin_restore_stops_the_countdown(tenant_a):
    sub = _end_trial(tenant_a, 31)
    retention.close(tenant_a, sub)
    retention.restore(tenant_a)
    tenant_a.refresh_from_db()
    assert tenant_a.is_active and retention.delete_on(sub) is None
    assert retention.run_daily() == {"warned": 0, "closed": 0, "deleted": 0}


def test_billing_page_shows_the_delete_date(client, tenant_a, tenant_a_owner):
    _end_trial(tenant_a, 2)
    client.force_login(tenant_a_owner)
    page = client.get(reverse("webapp:billing")).content.decode()
    assert "will be deleted on" in page and reverse("webapp:export_data") in page


def test_barcode_sheet_is_a_link_with_a_way_back(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    client.force_login(tenant_a_owner)
    url = reverse("webapp:barcode_print")
    page = client.get(url, {"print": 1, "product_ids": [data["product"].id, "x"], f"qty_{data['product'].id}": 3})
    html = page.content.decode()
    assert page.status_code == 200 and f'href="{url}"' in html and "Back" in html
    assert html.count('class="label') >= 3 or html.count("barcode") >= 3
    assert "product_ids" in client.get(url).content.decode()  # the picker still opens
