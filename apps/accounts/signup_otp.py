"""One-time code at sign-up: the account is made only after the person types the code we sent them.

SIGNUP_OTP picks where the code goes:
  "email"   - to the email address typed in the form (default; needs a working mail server)
  "sms"     - to the mobile number, through Twilio Verify (needs the three TWILIO_* settings)
  "console" - only written to the log (local testing)
  ""        - off: sign-up does not ask for a code
"""
import logging
import re
import secrets
import time

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)

CODE_MINUTES = 10
DIAL_CODES = {
    "Qatar": "974", "United Arab Emirates": "971", "Saudi Arabia": "966", "Oman": "968", "Kuwait": "965",
    "Bahrain": "973", "India": "91", "United Kingdom": "44", "United States": "1", "Canada": "1",
    "Australia": "61", "Germany": "49", "France": "33", "Ireland": "353", "Netherlands": "31",
    "Italy": "39", "Spain": "34",
}
TWILIO_VERIFY = "https://verify.twilio.com/v2/Services/{sid}/{what}"


class OtpError(Exception):
    """The code could not be sent or checked; the message is safe to show."""


def method():
    """The way codes go out right now, or "" when sign-up should not ask for one."""
    from apps.notifications.services import email_configured
    chosen = getattr(settings, "SIGNUP_OTP", "")
    if chosen == "email":
        return "email" if email_configured() else ""  # no mail server: a code could never arrive
    if chosen == "sms":
        return "sms" if getattr(settings, "TWILIO_VERIFY_SERVICE_SID", "") else ""
    return "console" if chosen == "console" else ""


def enabled():
    return bool(method())


def target(data):
    """Where the code goes for this sign-up: the mobile number for SMS, else the email address."""
    return data["phone"] if method() == "sms" else data["email"]


def masked(value):
    """anu@spice.test -> a••@spice.test, +919847554224 -> +919•••••4224"""
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:1]}{'•' * max(2, len(name) - 1)}@{domain}"
    return value[:4] + "•" * max(0, len(value) - 8) + value[-4:]


def normalize(phone, country=""):
    """'+91 98475 54224', '0091…' or '98475 54224' with country India -> '+919847554224'; '' if not a number."""
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


def send(to, session):
    """Send a fresh code. Raises OtpError."""
    how = method()
    if how == "sms":
        _twilio("Verifications", {"To": to, "Channel": getattr(settings, "PHONE_OTP_CHANNEL", "sms")})
        return
    code = f"{secrets.randbelow(10 ** 6):06d}"
    if how == "email":
        try:
            send_mail(
                _("Your BookPilot code: %(code)s") % {"code": code},
                "\n\n".join([
                    _("Your BookPilot sign-up code is %(code)s") % {"code": code},
                    _("It works for %(minutes)s minutes. If you did not try to create a BookPilot account, you can ignore this email.") % {"minutes": CODE_MINUTES},  # noqa: E501
                ]),
                None, [to],
            )
        except Exception:
            log.exception("Sign-up code email to %s failed", to)
            raise OtpError(_("We could not send the email. Check the address and try again."))
    else:
        log.warning("Sign-up code for %s: %s", to, code)
    session["otp_hash"] = make_password(code)
    session["otp_made_at"] = time.time()


def check(to, code, session):
    code = re.sub(r"\D", "", code or "")
    if len(code) < 4:
        return False
    if method() == "sms":
        return _twilio("VerificationCheck", {"To": to, "Code": code}).get("status") == "approved"
    stored = session.get("otp_hash")
    fresh = time.time() - session.get("otp_made_at", 0) < CODE_MINUTES * 60
    return bool(stored) and fresh and check_password(code, stored)


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
