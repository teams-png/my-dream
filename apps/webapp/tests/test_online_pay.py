"""Customers paying invoices online (SkipCash / Razorpay mocked) and the customer portal."""
import base64
import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.customers.models import Customer
from apps.inventory.services import record_stock_movement
from apps.notifications.models import Notification
from apps.sales import online_pay, services as sales, sharing
from apps.sales.models import CustomerPayment, OnlinePayment, OnlinePaymentSettings
from apps.webapp.pay_views import company_token

pytestmark = pytest.mark.django_db
PAYMENT_ID = "3f8b1c9e-2a6d-4c1b-9e0f-7a5d2b8c4e11"


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


@pytest.fixture
def shop(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="RICE", stock_price=Decimal("100"))
    record_stock_movement(company=tenant_a, product=base["product"], warehouse=base["warehouse"], quantity=50, reason="purchase")
    ali = Customer.objects.create(company=tenant_a, name="Ali Traders", phone="+97455551212", email="ali@t.qa")

    def invoice(days_ago, qty):
        return sales.create_invoice(company=tenant_a, user=tenant_a_owner, customer=ali, date=date.today() - timedelta(days=days_ago),
                                    lines=[{"product": base["product"], "quantity": Decimal(qty), "unit_price": Decimal("100")}],
                                    warehouse=base["warehouse"])
    return {"company": tenant_a, "owner": tenant_a_owner, "ali": ali, "old": invoice(40, 2), "new": invoice(1, 1),
            "client": client}


def _setup(company, provider="skipcash"):
    config = OnlinePaymentSettings.load(company)
    config.provider, config.key_id, config.client_id = provider, "key-1", "client-1"
    config.set_secret("secret", "secret-1")
    config.set_secret("webhook_key", "hook-1")
    config.instructions = "IBAN QA00 1234"
    config.save()
    return config


def test_public_invoice_shows_pay_now_only_when_set_up(shop):
    url = reverse("webapp:public_invoice", args=[sharing.share_token(shop["old"])])
    page = Client().get(url).content.decode()
    assert "Pay now" not in page
    _setup(shop["company"])
    page = Client().get(url).content.decode()
    assert "Pay now" in page and "IBAN QA00 1234" in page and "200.00" in page


def test_skipcash_pay_now_marks_invoice_paid_once(shop):
    _setup(shop["company"])
    token = sharing.share_token(shop["old"])
    public = Client()
    with mock.patch("apps.sales.online_pay.requests.post") as post:
        post.return_value = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "payUrl": "https://pay.test/x"}})
        resp = public.post(reverse("webapp:pay_invoice", args=[token]))
    assert resp.status_code == 302 and resp["Location"] == "https://pay.test/x"
    sent = post.call_args.kwargs["json"]
    assert sent["Amount"] == "200.00" and sent["KeyId"] == "key-1"
    payment = OnlinePayment.objects.for_company(shop["company"]).get()
    details = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "statusId": 2, "amount": "200.00",
                                                             "currency": "QAR", "transactionId": payment.transaction_id}})
    with mock.patch("apps.subscriptions.skipcash.requests.get", return_value=details):
        back = public.get(reverse("webapp:pay_return", args=[company_token(shop["company"])]) + f"?id={PAYMENT_ID}")
        public.get(reverse("webapp:pay_return", args=[company_token(shop["company"])]) + f"?id={PAYMENT_ID}")
    assert back.status_code == 302 and back["Location"].endswith("?paid=1")
    shop["old"].refresh_from_db()
    assert shop["old"].status == "paid"
    assert CustomerPayment.objects.for_company(shop["company"]).filter(invoice=shop["old"]).count() == 1
    payment.refresh_from_db()
    assert payment.status == "paid" and payment.receipts == shop["old"].invoice_number
    assert Notification.objects.filter(company=shop["company"], title__startswith="Online payment received").count() == 1


def test_amount_mismatch_is_not_recorded(shop):
    _setup(shop["company"])
    with mock.patch("apps.sales.online_pay.requests.post") as post:
        post.return_value = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "payUrl": "https://pay.test/x"}})
        payment, _url = online_pay.start(company=shop["company"], customer=shop["ali"], amount=Decimal("200"), invoice=shop["old"])
    details = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "statusId": 2, "amount": "1.00",
                                                             "currency": "QAR", "transactionId": payment.transaction_id}})
    with mock.patch("apps.subscriptions.skipcash.requests.get", return_value=details):
        online_pay.settle(payment)
    payment.refresh_from_db()
    assert payment.status == "pending" and "does not match" in payment.status_detail
    assert not CustomerPayment.objects.for_company(shop["company"]).exists()


def test_skipcash_webhook_needs_valid_signature(shop):
    _setup(shop["company"])
    with mock.patch("apps.sales.online_pay.requests.post") as post:
        post.return_value = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "payUrl": "https://pay.test/x"}})
        payment, _url = online_pay.start(company=shop["company"], customer=shop["ali"], amount=Decimal("200"), invoice=shop["old"])
    payload = {"PaymentId": PAYMENT_ID, "Amount": "200.00", "StatusId": 2, "TransactionId": payment.transaction_id}
    url = reverse("webapp:pay_webhook", args=[company_token(shop["company"])])
    bad = Client().post(url, json.dumps(payload), content_type="application/json", HTTP_AUTHORIZATION="nope")
    assert bad.status_code == 401
    message = ",".join(f"{k}={payload[k]}" for k in ["PaymentId", "Amount", "StatusId", "TransactionId"])
    sig = base64.b64encode(hmac.new(b"hook-1", message.encode(), hashlib.sha256).digest()).decode()
    details = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "statusId": 2, "amount": "200.00",
                                                             "currency": "QAR", "transactionId": payment.transaction_id}})
    with mock.patch("apps.subscriptions.skipcash.requests.get", return_value=details):
        ok = Client().post(url, json.dumps(payload), content_type="application/json", HTTP_AUTHORIZATION=sig)
    assert ok.status_code == 200 and ok.json()["status"] == "paid"


def test_portal_shows_bills_and_razorpay_pays_whole_balance(shop):
    _setup(shop["company"], provider="razorpay")
    token = online_pay.portal_token(shop["ali"])
    public = Client()
    page = public.get(reverse("webapp:customer_portal", args=[token]))
    assert page.status_code == 200
    html = page.content.decode()
    assert shop["old"].invoice_number in html and "300.00" in html and "Pay now" in html
    with mock.patch("apps.sales.online_pay.requests.post") as post:
        post.return_value = FakeResponse({"id": "plink_1", "short_url": "https://rzp.io/i/x"})
        resp = public.post(reverse("webapp:portal_pay", args=[token]))
    assert resp["Location"] == "https://rzp.io/i/x"
    body = post.call_args.kwargs["json"]
    assert body["amount"] == 30000 and "/pay/" in body["callback_url"] and "?p=" in body["callback_url"]
    payment = OnlinePayment.objects.for_company(shop["company"]).get()
    link = FakeResponse({"id": "plink_1", "status": "paid", "amount_paid": 30000, "currency": "QAR",
                         "reference_id": payment.transaction_id, "payments": [{"payment_id": "pay_9"}]})
    with mock.patch("apps.sales.online_pay.requests.get", return_value=link):
        back = public.get(body["callback_url"].split("testserver")[1] + "&razorpay_payment_id=pay_9")
    assert back["Location"].endswith("?paid=1") and "/c/" in back["Location"]
    for inv in (shop["old"], shop["new"]):
        inv.refresh_from_db()
        assert inv.status == "paid"
    assert Client().get(reverse("webapp:customer_portal", args=["bad-token"])).status_code == 404


def test_settings_page_owner_saves_and_secrets_are_encrypted(shop):
    client = shop["client"]
    client.force_login(shop["owner"])
    assert client.get(reverse("webapp:online_payment_settings")).status_code == 200
    client.post(reverse("webapp:online_payment_settings"), {
        "provider": "skipcash", "key_id": "k", "client_id": "c", "secret": "s3cret", "test_mode": "on",
        "instructions": "Fawran 5555", "portal_enabled": "on"})
    config = OnlinePaymentSettings.objects.get(company=shop["company"])
    assert config.ready and config.secret == "s3cret" and "s3cret" not in config.secret_ciphertext
    client.post(reverse("webapp:online_payment_settings"), {"provider": "skipcash", "key_id": "k", "client_id": "c"})
    config.refresh_from_db()
    assert config.secret == "s3cret"  # blank keeps the saved secret
    page = client.get(reverse("webapp:customer_account", args=[shop["ali"].id])).content.decode()
    assert "/c/" in page
