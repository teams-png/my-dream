"""
Customers pay a business's invoices online through the business's own gateway
(SkipCash in Qatar, Razorpay payment links in India).

A payment is never trusted from the browser redirect or a webhook body: both only
say *which* payment to look at, and the server then asks the gateway for its real
status and amount before the money is recorded against the customer's invoices.
"""
import logging
import uuid
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import requests
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.subscriptions import skipcash

from .allocation import allocate_payment
from .models import OnlinePayment, OnlinePaymentSettings

logger = logging.getLogger(__name__)
TIMEOUT = 20
RAZORPAY_API = "https://api.razorpay.com/v1"
PORTAL_SALT = "bookpilot.customer-portal"
PORTAL_MAX_AGE = 60 * 60 * 24 * 365


class PaymentError(Exception):
    pass


# ------------------------------------------------------------------ portal links

def portal_token(customer):
    return signing.dumps({"u": customer.id, "c": customer.company_id}, salt=PORTAL_SALT, compress=True)


def customer_from_portal_token(token):
    from apps.customers.models import Customer
    try:
        data = signing.loads(token, salt=PORTAL_SALT, max_age=PORTAL_MAX_AGE)
    except signing.BadSignature:
        return None
    return Customer._base_manager.select_related("company").filter(id=data.get("u"), company_id=data.get("c")).first()


def settings_for(company):
    return OnlinePaymentSettings.objects.filter(company=company).first()


def can_pay_online(company):
    config = settings_for(company)
    return bool(config and config.ready)


# ------------------------------------------------------------------ start

def start(*, company, customer, amount, invoice=None, return_url_for=lambda payment: ""):
    """Creates the payment at the gateway. Returns (OnlinePayment, url to send the customer to)."""
    config = settings_for(company)
    if not config or not config.ready:
        raise PaymentError("Online payment is not set up for this business.")
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise PaymentError("Nothing to pay.")
    currency = (invoice.currency if invoice else company.default_currency).upper()
    payment = OnlinePayment.objects.create(
        company=company, customer=customer, invoice=invoice, provider=config.provider, amount=amount, currency=currency,
        transaction_id=f"BPI-{company.id}-{uuid.uuid4().hex[:16]}")
    try:
        if config.provider == "skipcash":
            url = _skipcash_start(config, payment, customer)
        else:
            url = _razorpay_start(config, payment, customer, return_url_for(payment))
    except (requests.RequestException, skipcash.SkipCashError, PaymentError, KeyError, ValueError) as exc:
        payment.status, payment.status_detail = "failed", str(exc)[:255]
        payment.save(update_fields=["status", "status_detail"])
        raise PaymentError(str(exc)) from exc
    return payment, url


def _names(customer):
    parts = (customer.name or "Customer").split()
    return parts[0][:50], (" ".join(parts[1:]) or parts[0])[:50]


def _sc(config):
    """The shape apps.subscriptions.skipcash expects, filled with this business's own keys."""
    return SimpleNamespace(skipcash_test_mode=config.test_mode, skipcash_client_id=config.client_id,
                           skipcash_webhook_key=config.webhook_key)


def _skipcash_start(config, payment, customer):
    first, last = _names(customer)
    data = {
        "Uid": str(uuid.uuid4()), "KeyId": config.key_id, "Amount": f"{payment.amount:.2f}",
        "FirstName": first, "LastName": last, "Phone": (customer.phone or "")[:20] or "00000000",
        "Email": (customer.email or payment.company.email or "customer@example.com")[:100],
        "TransactionId": payment.transaction_id, "Custom1": f"invoice:{payment.invoice_id or 0}",
    }
    response = requests.post(f"{skipcash.base_url(_sc(config))}/api/v1/payments", json=data, timeout=TIMEOUT,
                             headers={"Authorization": skipcash.request_signature(config.secret, data),
                                      "x-client-id": config.client_id, "Content-Type": "application/json"})
    result = skipcash._result(response)
    payment.gateway_payment_id = str(result.get("id") or "")
    payment.save(update_fields=["gateway_payment_id"])
    if not result.get("payUrl"):
        raise PaymentError("SkipCash did not return a payment page.")
    return result["payUrl"]


def _razorpay_start(config, payment, customer, return_url):
    body = {
        "amount": int(payment.amount * 100), "currency": payment.currency, "reference_id": payment.transaction_id,
        "description": (f"Invoice {payment.invoice.invoice_number}" if payment.invoice else "Account payment")[:200],
        "customer": {k: v for k, v in {"name": customer.name[:100], "contact": customer.phone or "",
                                       "email": customer.email or ""}.items() if v},
        "callback_url": return_url, "callback_method": "get",
    }
    response = requests.post(f"{RAZORPAY_API}/payment_links", json=body, timeout=TIMEOUT, auth=(config.key_id, config.secret))
    data = response.json()
    if response.status_code >= 400 or not data.get("short_url"):
        raise PaymentError((data.get("error") or {}).get("description") or f"Razorpay answered with HTTP {response.status_code}.")
    payment.gateway_payment_id = data["id"]
    payment.save(update_fields=["gateway_payment_id"])
    return data["short_url"]


# ------------------------------------------------------------------ settle

def _gateway_status(config, payment):
    """(paid?, failed?, amount, currency, reference) as reported by the gateway itself."""
    if payment.provider == "skipcash":
        details = skipcash.fetch_payment(_sc(config), payment.gateway_payment_id)
        if str(details.get("transactionId") or "") != payment.transaction_id:
            raise PaymentError("Payment does not match.")
        try:
            status_id, amount = int(details.get("statusId")), Decimal(str(details.get("amount")))
        except (TypeError, ValueError, InvalidOperation):
            status_id, amount = None, None
        currency = (details.get("currency") or payment.currency).upper()
        return status_id == skipcash.PAID, status_id in skipcash.FAILED_STATUSES, amount, currency, payment.gateway_payment_id
    response = requests.get(f"{RAZORPAY_API}/payment_links/{payment.gateway_payment_id}", timeout=TIMEOUT,
                            auth=(config.key_id, config.secret))
    data = response.json()
    if response.status_code >= 400 or data.get("reference_id") != payment.transaction_id:
        raise PaymentError("Payment does not match.")
    amount = Decimal(int(data.get("amount_paid") or 0)) / 100
    ref = ((data.get("payments") or [{}])[-1] or {}).get("payment_id") or data.get("id")
    return data.get("status") == "paid", data.get("status") in ("cancelled", "expired"), amount, \
        (data.get("currency") or "").upper(), ref


def settle(payment):
    """Asks the gateway about the payment and, once paid in full, records it (only once)."""
    if payment.status != "pending" or not payment.gateway_payment_id:
        return payment
    config = settings_for(payment.company)
    if not config or config.provider != payment.provider:
        return payment
    try:
        paid, failed, amount, currency, ref = _gateway_status(config, payment)
    except (requests.RequestException, skipcash.SkipCashError, PaymentError, ValueError) as exc:
        logger.warning("Online payment %s could not be checked: %s", payment.pk, exc)
        return payment
    with transaction.atomic():
        payment = OnlinePayment._base_manager.select_for_update().select_related("company", "customer").get(pk=payment.pk)
        if payment.status != "pending":
            return payment
        if paid and amount == payment.amount and currency == payment.currency.upper():
            receipts, _left = allocate_payment(
                company=payment.company, user=_owner(payment.company), customer=payment.customer, amount=amount,
                date=timezone.localdate(), method=config.deposit_to if config.deposit_to == "cash" else "bank",
                invoice_id=payment.invoice_id if payment.invoice_id and payment.invoice.status != "paid" else None)
            payment.status, payment.paid_at, payment.status_detail = "paid", timezone.now(), str(ref)[:255]
            payment.receipts = ", ".join(receipts)[:255]
            payment.save(update_fields=["status", "paid_at", "status_detail", "receipts"])
            _notify_paid(payment)
        elif paid:
            payment.status_detail = f"Paid {amount} {currency} does not match {payment.amount} {payment.currency}."[:255]
            payment.save(update_fields=["status_detail"])
            logger.error("Online payment %s amount mismatch", payment.pk)
        elif failed:
            payment.status = "failed"
            payment.save(update_fields=["status"])
    return payment


def _owner(company):
    """Online payments have no cashier; the ledger entry is posted in the owner's name."""
    member = (company.memberships.filter(is_active=True, role__name="Owner").select_related("user").order_by("id").first()
              or company.memberships.select_related("user").order_by("id").first())
    return member.user


def _notify_paid(payment):
    try:
        from apps.notifications.services import notify
        notify(company=payment.company, notif_type="general",
               title=f"Online payment received: {payment.currency} {payment.amount:.2f} from {payment.customer.name}",
               message=f"Applied to {payment.receipts}." if payment.receipts else "Kept on the customer's account.")
    except Exception:  # a notification problem must never undo a received payment
        logger.exception("Could not notify about online payment %s", payment.pk)


def settle_skipcash_webhook(company, payload, signature):
    config = settings_for(company)
    if not config or config.provider != "skipcash" or not config.webhook_key:
        return None
    if not skipcash.valid_webhook(_sc(config), payload, signature):
        return None
    payment = OnlinePayment._base_manager.filter(company=company, transaction_id=str(payload.get("TransactionId") or "")).first()
    if payment is None:
        return None
    if not payment.gateway_payment_id:
        payment.gateway_payment_id = str(payload.get("PaymentId") or "")
    return settle(payment)
