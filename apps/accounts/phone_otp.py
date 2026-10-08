"""One-time codes sent by SMS to check a phone number (used at sign-up).

PHONE_OTP_BACKEND picks how the code goes out:
  "twilio"  - Twilio Verify makes, sends and checks the code (works in India, Qatar and the Gulf)
  "console" - we make the code and only write it to the log (local testing)
  ""        - off: sign-up does not ask for a code
"""
import logging
import re
import secrets

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)

DIAL_CODES = {
    "Qatar": "974", "United Arab Emirates": "971", "Saudi Arabia": "966", "Oman": "968", "Kuwait": "965",
    "Bahrain": "973", "India": "91", "United Kingdom": "44", "United States": "1", "Canada": "1",
    "Australia": "61", "Germany": "49", "France": "33", "Ireland": "353", "Netherlands": "31",
    "Italy": "39", "Spain": "34",
}
TWILIO_VERIFY = "https://verify.twilio.com/v2/Services/{sid}/{what}"


class OtpError(Exception):
    """The code could not be sent or checked; the message is safe to show."""


def enabled():
    return backend() in ("twilio", "console")


def backend():
    return getattr(settings, "PHONE_OTP_BACKEND", "")


def normalize(phone, country=""):
    """'+91 98475 54224', '0098475…' or '98475 54224' with country India -> '+919847554224'; '' if not a number."""
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("00"):
        digits, raw = digits[2:], "+" + digits[2:]
    if not raw.startswith("+"):
        code = DIAL_CODES.get(country)
        if not code:
            return ""
        digits = code + digits.lstrip("0")
    return f"+{digits}" if 8 <= len(digits) <= 15 else ""


def send(phone, session):
    """Send a fresh code to phone (E.164). Raises OtpError."""
    if backend() == "twilio":
        _twilio("Verifications", {"To": phone, "Channel": getattr(settings, "PHONE_OTP_CHANNEL", "sms")})
    else:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        session["phone_otp_hash"] = make_password(code)
        log.warning("Sign-up code for %s: %s", phone, code)


def check(phone, code, session):
    code = re.sub(r"\D", "", code or "")
    if len(code) < 4:
        return False
    if backend() == "twilio":
        return _twilio("VerificationCheck", {"To": phone, "Code": code}).get("status") == "approved"
    stored = session.get("phone_otp_hash")
    return bool(stored) and check_password(code, stored)


def _twilio(what, data):
    url = TWILIO_VERIFY.format(sid=settings.TWILIO_VERIFY_SERVICE_SID, what=what)
    try:
        r = requests.post(url, data=data, timeout=10,
                          auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
    except requests.RequestException:
        log.exception("Twilio Verify %s failed", what)
        raise OtpError(_("We could not reach the SMS service. Please try again in a minute."))
    if what == "VerificationCheck" and r.status_code == 404:
        return {}  # code expired or already used
    if r.status_code >= 400:
        log.error("Twilio Verify %s returned %s: %s", what, r.status_code, r.text[:300])
        raise OtpError(_("We could not send a code to this number. Check the number and try again."))
    return r.json()
