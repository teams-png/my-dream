"""
SkipCash (Qatar) hosted checkout for subscription payments.

Request signing follows SkipCash's own SDK: the non-empty fields are joined
as "Key=value" pairs in a fixed order, separated by commas, signed with
HMAC-SHA256 using the key secret, and sent base64-encoded in the
Authorization header.

A payment is never trusted from the browser redirect or the webhook body
alone: both only tell us *which* payment to look at, and the server then
asks SkipCash for that payment's real status and amount.
"""
import base64
import hashlib
import hmac
import logging
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction
from django.utils import timezone

from .models import GatewayCheckout

logger = logging.getLogger(__name__)

SANDBOX_URL = "https://skipcashtest.azurewebsites.net"
PRODUCTION_URL = "https://api.skipcash.app"
PAID = 2  # SkipCash StatusId for a completed payment
FAILED_STATUSES = {3, 4}  # cancelled, failed
REQUEST_FIELDS = ["Uid", "KeyId", "Amount", "FirstName", "LastName", "Phone", "Email",
                  "Street", "City", "State", "Country", "PostalCode", "TransactionId"]
WEBHOOK_FIELDS = ["PaymentId", "Amount", "StatusId", "TransactionId", "Custom1", "VisaId"]
TIMEOUT = 20


class SkipCashError(Exception):
    pass


def base_url(config):
    return SANDBOX_URL if config.skipcash_test_mode else PRODUCTION_URL


def _sign(secret, message):
    return base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()


def request_signature(secret, data):
    parts = [f"{k}={data[k]}" for k in REQUEST_FIELDS if data.get(k)]
    extra = [f"{k}={v}" for k, v in data.items() if k not in REQUEST_FIELDS and v]
    if extra:
        parts.append(extra[0])  # SkipCash signs only the first custom field
    return _sign(secret, ",".join(parts))


def webhook_signature(secret, payload):
    return _sign(secret, ",".join(f"{k}={payload[k]}" for k in WEBHOOK_FIELDS if payload.get(k) not in (None, "")))


def valid_webhook(config, payload, signature):
    if not config.skipcash_webhook_key or not signature or not isinstance(payload, dict):
        return False
    return hmac.compare_digest(webhook_signature(config.skipcash_webhook_key, payload), signature)


def _result(response):
    try:
        body = response.json()
    except ValueError:
        raise SkipCashError(f"SkipCash answered with HTTP {response.status_code}.")
    if response.status_code >= 400 or body.get("returnCode") not in (200, None) or not body.get("resultObj"):
        errors = "; ".join(e.get("errorMessage", "") for e in body.get("validationErrors") or [] if isinstance(e, dict))
        raise SkipCashError(errors or body.get("errorMessage") or f"SkipCash answered with HTTP {response.status_code}.")
    return body["resultObj"]


def start_checkout(config, *, subscription, user, first_name, last_name, phone, email):
    """Creates the payment at SkipCash and returns (GatewayCheckout, pay_url)."""
    from .pricing import amount_due
    plan = subscription.plan
    amount = amount_due(subscription)
    checkout = GatewayCheckout.objects.create(
        subscription=subscription, gateway="skipcash", transaction_id=f"BP-{subscription.id}-{uuid.uuid4().hex[:12]}",
        amount=amount, currency=plan.currency, created_by=user,
    )
    data = {
        "Uid": str(uuid.uuid4()), "KeyId": config.skipcash_key_id, "Amount": f"{amount:.2f}",
        "FirstName": (first_name or "Customer")[:50], "LastName": (last_name or first_name or "Customer")[:50],
        "Phone": phone[:20], "Email": email[:100], "TransactionId": checkout.transaction_id,
        "Custom1": f"subscription:{subscription.id}",
    }
    try:
        response = requests.post(f"{base_url(config)}/api/v1/payments", json=data, timeout=TIMEOUT, headers={
            "Authorization": request_signature(config.skipcash_key_secret, data),
            "x-client-id": config.skipcash_client_id, "Content-Type": "application/json",
        })
        result = _result(response)
    except (requests.RequestException, SkipCashError) as exc:
        checkout.status, checkout.status_detail = "failed", str(exc)[:255]
        checkout.save(update_fields=["status", "status_detail"])
        raise SkipCashError(str(exc)) from exc
    checkout.gateway_payment_id = str(result.get("id") or "")
    checkout.save(update_fields=["gateway_payment_id"])
    if not result.get("payUrl"):
        raise SkipCashError("SkipCash did not return a payment page.")
    return checkout, result["payUrl"]


def fetch_payment(config, payment_id):
    try:
        uuid.UUID(str(payment_id))
    except ValueError:
        raise SkipCashError("Invalid payment id.")
    try:
        response = requests.get(f"{base_url(config)}/api/v1/payments/{payment_id}", timeout=TIMEOUT,
                                headers={"Authorization": config.skipcash_client_id})
    except requests.RequestException as exc:
        raise SkipCashError(str(exc)) from exc
    return _result(response)


def settle(config, payment_id):
    """
    Looks the payment up at SkipCash and, if it is paid in full, renews the
    subscription once. Returns the GatewayCheckout (or None if unknown).
    """
    from .services import confirm_gateway_payment

    details = fetch_payment(config, payment_id)
    transaction_id = str(details.get("transactionId") or "")
    with transaction.atomic():
        checkout = (GatewayCheckout.objects.select_for_update().select_related("subscription__plan")
                    .filter(gateway="skipcash", transaction_id=transaction_id).first())
        if checkout is None:
            logger.warning("SkipCash payment %s has unknown transaction id %r", payment_id, transaction_id)
            return None
        if checkout.status == "paid":
            return checkout
        if checkout.gateway_payment_id and checkout.gateway_payment_id != str(payment_id):
            logger.warning("SkipCash payment %s does not belong to checkout %s", payment_id, checkout.pk)
            return checkout
        try:
            status_id = int(details.get("statusId"))
            amount = Decimal(str(details.get("amount")))
        except (TypeError, ValueError, InvalidOperation):
            status_id, amount = None, None
        currency = (details.get("currency") or checkout.currency or "").upper()
        if status_id == PAID and amount == checkout.amount and currency == checkout.currency.upper():
            checkout.status, checkout.paid_at, checkout.status_detail = "paid", timezone.now(), ""
            checkout.gateway_payment_id = str(payment_id)
            checkout.save(update_fields=["status", "paid_at", "status_detail", "gateway_payment_id"])
            confirm_gateway_payment(checkout.subscription, amount=amount, reference=str(payment_id), method="skipcash")
        elif status_id == PAID:
            checkout.status_detail = f"Paid amount {amount} {currency} does not match {checkout.amount} {checkout.currency}."
            checkout.save(update_fields=["status_detail"])
            logger.error("SkipCash amount mismatch for checkout %s: %s", checkout.pk, checkout.status_detail)
        elif status_id in FAILED_STATUSES:
            checkout.status, checkout.status_detail = "failed", str(details.get("status") or "")[:255]
            checkout.save(update_fields=["status", "status_detail"])
    return checkout
