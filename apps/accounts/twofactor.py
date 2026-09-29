"""
Two-factor authentication with authenticator apps (Google Authenticator,
Microsoft Authenticator, Authy, 1Password…). Standard library TOTP:
30-second steps, 6 digits, SHA-1, one step of clock drift allowed.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.platform_admin.payment_gateways import decrypt_credential, encrypt_credential

from .models import TwoFactorDevice

STEP = 30
DIGITS = 6
ISSUER = "BookPilot"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code_at(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def current_code(secret, at=None):
    return _code_at(secret, int((at or time.time()) // STEP))


def matching_step(secret, code, at=None, window=1):
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = int((at or time.time()) // STEP)
    for step in range(now - window, now + window + 1):
        if hmac.compare_digest(_code_at(secret, step), code):
            return step
    return None


def provisioning_uri(user, secret):
    label = quote(f"{ISSUER}:{user.email or user.username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP}"


def qr_svg(uri):
    import qrcode
    import qrcode.image.svg
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return image.to_string(encoding="unicode")


def is_enabled(user):
    if not getattr(user, "pk", None):
        return False
    return TwoFactorDevice.objects.filter(user_id=user.pk, confirmed=True).exists()


def start_setup(user):
    """Creates (or restarts) an unconfirmed device and returns the plain secret."""
    secret = new_secret()
    TwoFactorDevice.objects.update_or_create(user=user, defaults={
        "secret_encrypted": encrypt_credential(secret), "confirmed": False,
        "recovery_code_hashes": [], "last_used_step": 0, "confirmed_at": None,
    })
    return secret


def secret_for(device):
    return decrypt_credential(device.secret_encrypted)


def _new_recovery_codes(n=8):
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def confirm_setup(user, code):
    """Verifies the first code; returns the one-time recovery codes, or None."""
    device = TwoFactorDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        return None
    step = matching_step(secret_for(device), code)
    if step is None:
        return None
    codes = _new_recovery_codes()
    device.recovery_code_hashes = [make_password(c) for c in codes]
    device.confirmed = True
    device.confirmed_at = timezone.now()
    device.last_used_step = step
    device.save()
    return codes


def verify(user, code):
    """Checks an authenticator code or a recovery code (recovery codes work once)."""
    device = TwoFactorDevice.objects.filter(user=user, confirmed=True).first()
    if device is None or not code:
        return False
    step = matching_step(secret_for(device), code)
    if step is not None and step > device.last_used_step:
        device.last_used_step = step
        device.save(update_fields=["last_used_step"])
        return True
    cleaned = str(code).strip().lower()
    for i, hashed in enumerate(device.recovery_code_hashes):
        if check_password(cleaned, hashed):
            device.recovery_code_hashes = device.recovery_code_hashes[:i] + device.recovery_code_hashes[i + 1:]
            device.save(update_fields=["recovery_code_hashes"])
            return True
    return False


def regenerate_recovery_codes(user):
    device = TwoFactorDevice.objects.get(user=user, confirmed=True)
    codes = _new_recovery_codes()
    device.recovery_code_hashes = [make_password(c) for c in codes]
    device.save(update_fields=["recovery_code_hashes"])
    return codes


def disable(user):
    TwoFactorDevice.objects.filter(user=user).delete()


def remaining_recovery_codes(user):
    device = TwoFactorDevice.objects.filter(user=user, confirmed=True).first()
    return len(device.recovery_code_hashes) if device else 0
