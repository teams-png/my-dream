"""Platform admin client billing: invoices, payments, expiry dates and money owed."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.subscriptions import billing
from apps.subscriptions.models import SubscriptionInvoice, SubscriptionPayment
from apps.subscriptions.services import approve_client_payment, confirm_gateway_payment, submit_client_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def sub(tenant_a):
    s = tenant_a.subscription
    s.plan.price, s.plan.currency, s.plan.billing_period = Decimal("199.00"), "QAR", "monthly"
    s.plan.save()
    tenant_a.phone = "+974 5555 1234"
    tenant_a.save(update_fields=["phone"])
    return s


def _admin():
    user = User.objects.create_superuser(username="boss@bp.qa", email="boss@bp.qa", password="Boss-Pass-123", is_platform_admin=True)
    client = Client()
    client.force_login(user)
    return client


def test_payment_keeps_the_days_left_and_makes_a_paid_invoice(sub):
    today = timezone.localdate()
    sub.end_date = today + timedelta(days=10)
    sub.save(update_fields=["end_date"])
    payment = billing.record_payment(sub, amount="199", method="bank", reference="TT-55")
    sub.refresh_from_db()
    assert sub.end_date == today + timedelta(days=40) and sub.status == "active"
    inv = payment.invoice
    assert inv.status == "paid" and inv.amount == Decimal("199.00") and inv.number == f"BP-{today:%Y}-{inv.pk:05d}"
    assert (inv.period_start, inv.period_end) == (today + timedelta(days=10), today + timedelta(days=40))
    for bad in ("0", "-5", "abc"):
        with pytest.raises(ValidationError):
            billing.record_payment(sub, amount=bad)


def test_expired_client_renews_from_today(sub):
    today = timezone.localdate()
    sub.end_date, sub.status = today - timedelta(days=20), "expired"
    sub.save(update_fields=["end_date", "status"])
    billing.record_payment(sub, amount="199")
    sub.refresh_from_db()
    assert sub.end_date == today + timedelta(days=30)


def test_invoice_first_then_payment(sub):
    inv = billing.issue_invoice(sub)
    assert inv.status == "unpaid" and inv.amount == Decimal("199.00") and inv.period_start == max(sub.end_date, timezone.localdate())
    assert billing.issue_invoice(sub).pk == inv.pk  # same period: not issued twice
    billing.record_payment(sub, amount="199", invoice=inv)
    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.status == "paid" and inv.payment is not None and sub.end_date == inv.period_end
    assert SubscriptionInvoice.objects.filter(subscription=sub).count() == 1
    with pytest.raises(ValidationError):
        billing.void_invoice(inv)
    with pytest.raises(ValidationError):
        billing.record_payment(sub, amount="199", invoice=inv)  # already paid
    nxt = billing.issue_invoice(sub, amount="150", notes="Discount")
    billing.void_invoice(nxt)
    assert SubscriptionInvoice.objects.get(pk=nxt.pk).status == "void"


def test_online_and_approved_payments_settle_the_open_invoice(sub):
    inv = billing.issue_invoice(sub)
    confirm_gateway_payment(sub, amount=Decimal("199"), reference="SC-1", method="skipcash")
    inv.refresh_from_db()
    assert inv.status == "paid" and inv.payment.reference == "SC-1"

    pending = submit_client_payment(sub, amount=Decimal("199"), method="bank", reference="TT-9")
    assert not SubscriptionInvoice.objects.filter(payment=pending).exists()
    approve_client_payment(pending)
    paid = SubscriptionInvoice.objects.get(payment=pending)
    assert paid.status == "paid" and paid.amount == Decimal("199.00")
    assert SubscriptionPayment.objects.filter(subscription=sub, invoice__isnull=True).count() == 0


def test_billing_list_filters_and_totals(sub, tenant_b):
    today = timezone.localdate()
    billing.record_payment(sub, amount="199")
    billing.record_payment(sub, amount="199")
    billing.issue_invoice(sub)
    other = tenant_b.subscription
    other.end_date = today - timedelta(days=3)
    other.save(update_fields=["end_date"])
    rows = {r["s"].pk: r for r in billing.overview()}
    assert rows[sub.pk]["paid"] == Decimal("398.00") and rows[sub.pk]["unpaid"] == Decimal("199.00")  # no double count
    assert rows[other.pk]["state"] == "expired" and rows[other.pk]["paid"] == 0
    assert [r["s"].pk for r in billing.overview(show="expired")] == [other.pk]
    assert [r["s"].pk for r in billing.overview(show="unpaid")] == [sub.pk]
    assert [r["s"].pk for r in billing.overview(q="power")] == [other.pk]
    t = billing.totals()
    assert t["month"] == Decimal("398.00") and t["unpaid"] == Decimal("199.00") and t["expired"] == 1
    link = billing.reminder_link(sub, app_url="https://app.test/billing/")
    assert link.startswith("https://wa.me/97455551234?text=") and "199.00" in link


def test_billing_pages(sub, tenant_a_owner, tenant_b_owner):
    admin = _admin()
    page = admin.get(reverse("webapp:platform_billing"))
    assert page.status_code == 200 and "ABC Textile" in page.content.decode()
    for show in ("expiring", "expired", "trial", "unpaid", "paying", "bogus"):
        assert admin.get(reverse("webapp:platform_billing") + f"?show={show}").status_code == 200
    url = reverse("webapp:platform_billing_client", args=[sub.company.id])
    assert "wa.me/97455551234" in admin.get(url).content.decode()
    admin.post(url, {"action": "issue", "amount": "199", "due_on": "", "notes": ""})
    inv = SubscriptionInvoice.objects.get(subscription=sub)
    admin.post(url, {"action": "pay", "amount": "199", "method": "cash", "reference": "R1", "paid_on": "", "invoice": inv.id})
    inv.refresh_from_db()
    assert inv.status == "paid" and inv.payment.method == "cash"
    printed = admin.get(reverse("webapp:platform_billing_invoice", args=[inv.id])).content.decode()
    assert inv.number in printed and "PAID" in printed and "ABC Textile" in printed

    owner = Client()
    owner.force_login(tenant_a_owner)
    assert owner.get(reverse("webapp:platform_billing")).status_code in (302, 403)
    assert inv.number in owner.get(reverse("webapp:billing")).content.decode()
    assert owner.get(reverse("webapp:client_billing_invoice", args=[inv.id])).status_code == 200
    stranger = Client()
    stranger.force_login(tenant_b_owner)
    assert stranger.get(reverse("webapp:client_billing_invoice", args=[inv.id])).status_code == 404
