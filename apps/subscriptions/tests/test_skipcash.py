"""SkipCash (Qatar) subscription payments, with the SkipCash API mocked."""
import base64
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.platform_admin.payment_gateways import get_payment_gateway_config
from apps.subscriptions import skipcash
from apps.subscriptions.models import GatewayCheckout, SubscriptionPayment
from apps.subscriptions.services import TRIAL_DAYS

pytestmark = pytest.mark.django_db

KEYS = dict(SKIPCASH_CLIENT_ID="client-1", SKIPCASH_KEY_ID="key-1", SKIPCASH_KEY_SECRET="secret-1",
            SKIPCASH_WEBHOOK_KEY="hook-1", SKIPCASH_TEST_MODE=True)
PAYMENT_ID = "3f8b1c9e-2a6d-4c1b-9e0f-7a5d2b8c4e11"


def _sig(secret, message):
    return base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


@pytest.fixture
def paid_plan(tenant_a):
    sub = tenant_a.subscription
    sub.plan.price, sub.plan.currency, sub.plan.billing_period = Decimal("199.00"), "QAR", "monthly"
    sub.plan.save()
    return sub


def _start(sub, user):
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.post") as post:
        post.return_value = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "payUrl": "https://pay.test/x"}})
        checkout, url = skipcash.start_checkout(get_payment_gateway_config(), subscription=sub, user=user,
                                                first_name="Sam", last_name="Lee", phone="+97455551234", email="s@x.qa")
    return checkout, url, post


def _details(checkout, status_id=2, amount="199.00"):
    return FakeResponse({"returnCode": 200, "resultObj": {
        "id": PAYMENT_ID, "statusId": status_id, "amount": amount, "currency": "QAR",
        "transactionId": checkout.transaction_id, "status": "Paid" if status_id == 2 else "Canceled"}})


def test_trial_is_three_days():
    assert TRIAL_DAYS == 3


def test_request_is_signed_like_skipcash_sdk(paid_plan, tenant_a_owner):
    checkout, url, post = _start(paid_plan, tenant_a_owner)
    assert url == "https://pay.test/x" and checkout.gateway_payment_id == PAYMENT_ID
    sent, headers = post.call_args.kwargs["json"], post.call_args.kwargs["headers"]
    assert post.call_args.args[0] == "https://skipcashtest.azurewebsites.net/api/v1/payments"
    expected = ",".join([f"Uid={sent['Uid']}", "KeyId=key-1", "Amount=199.00", "FirstName=Sam", "LastName=Lee",
                         "Phone=+97455551234", "Email=s@x.qa", f"TransactionId={checkout.transaction_id}",
                         f"Custom1=subscription:{paid_plan.id}"])
    assert headers["Authorization"] == _sig("secret-1", expected)
    assert headers["x-client-id"] == "client-1"


def test_paid_payment_renews_once(paid_plan, tenant_a_owner):
    checkout, _url, _post = _start(paid_plan, tenant_a_owner)
    before = paid_plan.end_date
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.get", return_value=_details(checkout)):
        skipcash.settle(get_payment_gateway_config(), PAYMENT_ID)
        skipcash.settle(get_payment_gateway_config(), PAYMENT_ID)  # webhook + return page
    paid_plan.refresh_from_db()
    checkout.refresh_from_db()
    assert checkout.status == "paid" and paid_plan.status == "active"
    assert paid_plan.end_date == max(before, timezone.localdate()) + timedelta(days=30)
    assert SubscriptionPayment.objects.filter(subscription=paid_plan, method="skipcash").count() == 1


@pytest.mark.parametrize("status_id,amount", [(2, "1.00"), (1, "199.00")])
def test_wrong_amount_or_unpaid_does_not_renew(paid_plan, tenant_a_owner, status_id, amount):
    checkout, _url, _post = _start(paid_plan, tenant_a_owner)
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.get",
                                               return_value=_details(checkout, status_id, amount)):
        skipcash.settle(get_payment_gateway_config(), PAYMENT_ID)
    checkout.refresh_from_db()
    assert checkout.status == "pending"
    assert not SubscriptionPayment.objects.filter(subscription=paid_plan).exists()


def test_cancelled_payment_is_marked_failed(paid_plan, tenant_a_owner):
    checkout, _url, _post = _start(paid_plan, tenant_a_owner)
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.get",
                                               return_value=_details(checkout, 3)):
        skipcash.settle(get_payment_gateway_config(), PAYMENT_ID)
    checkout.refresh_from_db()
    assert checkout.status == "failed"


def test_webhook_needs_valid_signature_then_checks_with_skipcash(client, paid_plan, tenant_a_owner):
    checkout, _url, _post = _start(paid_plan, tenant_a_owner)
    payload = {"PaymentId": PAYMENT_ID, "Amount": "199.00", "StatusId": 2, "TransactionId": checkout.transaction_id,
               "Custom1": f"subscription:{paid_plan.id}", "VisaId": "", "TokenId": "", "CardType": "1"}
    good = _sig("hook-1", f"PaymentId={PAYMENT_ID},Amount=199.00,StatusId=2,TransactionId={checkout.transaction_id},"
                          f"Custom1=subscription:{paid_plan.id}")
    url = reverse("webapp:billing_skipcash_webhook")
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.get", return_value=_details(checkout)):
        bad = client.post(url, json.dumps(payload), content_type="application/json", HTTP_AUTHORIZATION="forged")
        assert bad.status_code == 401
        ok = client.post(url, json.dumps(payload), content_type="application/json", HTTP_AUTHORIZATION=good)
    assert ok.status_code == 200
    checkout.refresh_from_db()
    assert checkout.status == "paid"


def test_billing_page_start_and_return(client, paid_plan, tenant_a_owner):
    client.force_login(tenant_a_owner)
    with override_settings(**KEYS):
        page = client.get(reverse("webapp:billing"))
        assert page.context["skipcash_ready"] and b"billing/skipcash/start" in page.content
        with mock.patch("apps.subscriptions.skipcash.requests.post") as post:
            post.return_value = FakeResponse({"returnCode": 200, "resultObj": {"id": PAYMENT_ID, "payUrl": "https://pay.test/x"}})
            bad_phone = client.post(reverse("webapp:billing_skipcash_start"), {"phone": "12"})
            assert bad_phone.url == reverse("webapp:billing") and not post.called
            resp = client.post(reverse("webapp:billing_skipcash_start"), {"phone": "+974 5555 1234"})
        assert resp.status_code == 302 and resp.url == "https://pay.test/x"
        checkout = GatewayCheckout.objects.get(subscription=paid_plan)
        with mock.patch("apps.subscriptions.skipcash.requests.get", return_value=_details(checkout)):
            back = client.get(reverse("webapp:billing_skipcash_return") + f"?id={PAYMENT_ID}", follow=True)
    assert "Payment received" in back.content.decode()
    paid_plan.refresh_from_db()
    assert paid_plan.status == "active"


def test_not_offered_when_disabled_or_not_qar(client, paid_plan, tenant_a_owner):
    client.force_login(tenant_a_owner)
    assert client.get(reverse("webapp:billing")).context["skipcash_ready"] is False  # no keys
    paid_plan.plan.currency = "INR"
    paid_plan.plan.save()
    with override_settings(**KEYS):
        assert client.get(reverse("webapp:billing")).context["skipcash_ready"] is False
        resp = client.post(reverse("webapp:billing_skipcash_start"), {"phone": "+97455551234"})
    assert resp.url == reverse("webapp:billing")
    assert not GatewayCheckout.objects.exists()


def test_not_offered_for_free_plan(client, paid_plan, tenant_a_owner):
    paid_plan.plan.price = Decimal("0")
    paid_plan.plan.save()
    client.force_login(tenant_a_owner)
    with override_settings(**KEYS):
        assert client.get(reverse("webapp:billing")).context["skipcash_ready"] is False


def test_only_owner_can_start(client, paid_plan, member_factory, tenant_a):
    staff = member_factory(tenant_a, "Staff")
    client.force_login(staff)
    with override_settings(**KEYS), mock.patch("apps.subscriptions.skipcash.requests.post") as post:
        client.post(reverse("webapp:billing_skipcash_start"), {"phone": "+97455551234"})
    assert not post.called
