import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _encryption_key():
    source = settings.PAYMENT_CREDENTIALS_ENCRYPTION_KEY
    if not source:
        raise RuntimeError("PAYMENT_CREDENTIALS_ENCRYPTION_KEY is not configured.")
    return hashlib.sha256(source.encode("utf-8")).digest()


def encrypt_credential(value):
    if not value:
        return ""
    nonce = os.urandom(12)
    encrypted = AESGCM(_encryption_key()).encrypt(nonce, value.encode("utf-8"), b"bookpilot-payment-v1")
    return "v1:" + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_credential(value):
    if not value:
        return ""
    if not value.startswith("v1:"):
        raise ValueError("Unsupported payment credential format.")
    payload = base64.urlsafe_b64decode(value[3:].encode("ascii"))
    plaintext = AESGCM(_encryption_key()).decrypt(payload[:12], payload[12:], b"bookpilot-payment-v1")
    return plaintext.decode("utf-8")


@dataclass(frozen=True)
class PaymentGatewayConfig:
    stripe_enabled: bool
    stripe_test_mode: bool
    stripe_publishable_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    razorpay_enabled: bool
    razorpay_test_mode: bool
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str


def get_payment_gateway_config():
    """Database values override environment variables; environment remains a safe fallback."""
    from .models import PaymentGatewaySettings

    saved = PaymentGatewaySettings.objects.filter(pk=1).first()

    def secret(name, environment_name):
        if saved:
            value = saved.get_secret(name)
            if value:
                return value
        return getattr(settings, environment_name, "")

    stripe_secret = secret("stripe_secret_key", "STRIPE_SECRET_KEY")
    razorpay_key_id = secret("razorpay_key_id", "RAZORPAY_KEY_ID")
    return PaymentGatewayConfig(
        stripe_enabled=(saved.stripe_enabled if saved else bool(stripe_secret)) and bool(stripe_secret),
        stripe_test_mode=saved.stripe_test_mode if saved else True,
        stripe_publishable_key=secret("stripe_publishable_key", "STRIPE_PUBLISHABLE_KEY"),
        stripe_secret_key=stripe_secret,
        stripe_webhook_secret=secret("stripe_webhook_secret", "STRIPE_WEBHOOK_SECRET"),
        razorpay_enabled=(saved.razorpay_enabled if saved else bool(razorpay_key_id)) and bool(razorpay_key_id),
        razorpay_test_mode=saved.razorpay_test_mode if saved else True,
        razorpay_key_id=razorpay_key_id,
        razorpay_key_secret=secret("razorpay_key_secret", "RAZORPAY_KEY_SECRET"),
        razorpay_webhook_secret=secret("razorpay_webhook_secret", "RAZORPAY_WEBHOOK_SECRET"),
    )
