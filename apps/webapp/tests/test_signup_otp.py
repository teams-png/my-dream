"""Sign-up sends an SMS code to the mobile number; the account is made only after the code is typed."""
import re

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounts import phone_otp
from apps.accounts.models import LoginAttempt, User
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def otp_on(settings):
    call_command("seed_platform")
    settings.PHONE_OTP_BACKEND = "console"


def _data(**over):
    data = {"business_name": "Spice Garden", "business_type": "restaurant", "country": "India",
            "full_name": "Anu Thomas", "email": "anu@spice.test", "phone": "98475 54224",
            "password": "Tasty-Food-2026!", "accept_terms": "on", "website": ""}
    data.update(over)
    return data


def _code(caplog):
    return re.findall(r"Sign-up code for \S+: (\d{6})", caplog.text)[-1]


def test_normalize():
    assert phone_otp.normalize("98475 54224", "India") == "+919847554224"
    assert phone_otp.normalize("+91 98475-54224", "Qatar") == "+919847554224"
    assert phone_otp.normalize("0097455551234", "India") == "+97455551234"
    assert phone_otp.normalize("5555 1234", "Qatar") == "+97455551234"
    assert phone_otp.normalize("12", "Qatar") == "" and phone_otp.normalize("5555 1234", "Other") == ""


def test_code_then_account(client, caplog):
    page = client.get(reverse("webapp:signup")).content.decode()
    assert "Mobile number" in page and "We will send a code" in page
    r = client.post(reverse("webapp:signup"), _data())
    assert r.url == reverse("webapp:signup_verify")
    assert not User.objects.filter(email="anu@spice.test").exists()  # nothing is made before the code
    pending = client.session["pending_signup"]
    assert "password" not in pending and pending["password_hash"].startswith(("md5$", "pbkdf2", "argon2"))
    page = client.get(reverse("webapp:signup_verify")).content.decode()
    assert "+919•••••4224" in page and "Tasty-Food" not in page

    code = _code(caplog)
    wrong = "000000" if code != "000000" else "111111"
    r = client.post(reverse("webapp:signup_verify"), {"code": wrong})
    assert r.url == reverse("webapp:signup_verify") and not User.objects.filter(email="anu@spice.test").exists()
    r = client.post(reverse("webapp:signup_verify"), {"code": code})
    assert r.url == reverse("webapp:setup", kwargs={"step": "business"})
    user = User.objects.get(email="anu@spice.test")
    assert user.phone == "+919847554224" and user.phone_verified and user.check_password("Tasty-Food-2026!")
    assert Company.objects.get(name="Spice Garden").country == "India"
    assert "pending_signup" not in client.session


def test_phone_rules(client, caplog):
    page = client.post(reverse("webapp:signup"), _data(phone="")).content.decode()
    assert "This field is required" in page
    page = client.post(reverse("webapp:signup"), _data(phone="123")).content.decode()
    assert "valid mobile number" in page
    User.objects.create_user(username="old@x.test", email="old@x.test", password="x", phone="+919847554224",
                             phone_verified=True)
    page = client.post(reverse("webapp:signup"), _data()).content.decode()
    assert "mobile number already exists" in page


def test_limits(client, caplog, settings):
    client.post(reverse("webapp:signup"), _data())
    # resend waits a minute
    client.post(reverse("webapp:signup_verify"), {"action": "resend"})
    assert LoginAttempt.objects.filter(identifier="otp-send:+919847554224").count() == 1
    # five wrong codes, then a new code is needed
    for _ in range(6):
        client.post(reverse("webapp:signup_verify"), {"code": "999999" if _code(caplog) != "999999" else "888888"})
    client.post(reverse("webapp:signup_verify"), {"code": _code(caplog)})
    assert not User.objects.filter(email="anu@spice.test").exists()
    # sends per number per hour
    settings.PHONE_OTP_SENDS_PER_HOUR = 1
    s = client.session
    s["otp_sent_at"] = 0
    s.save()
    page = client.post(reverse("webapp:signup_verify"), {"action": "resend"}, follow=True).content.decode()
    assert "Too many codes" in page


def test_change_number_keeps_the_form(client):
    client.post(reverse("webapp:signup"), _data())
    page = client.get(reverse("webapp:signup") + "?edit=1").content.decode()
    assert "Spice Garden" in page and "anu@spice.test" in page and "Tasty-Food" not in page


def test_twilio_backend(client, settings, monkeypatch):
    settings.PHONE_OTP_BACKEND = "twilio"
    settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_VERIFY_SERVICE_SID = "AC1", "tok", "VA1"
    calls = []

    class Resp:
        def __init__(self, status, body):
            self.status_code, self._body, self.text = status, body, str(body)

        def json(self):
            return self._body

    def fake_post(url, data, timeout, auth):
        calls.append((url, data, auth))
        if url.endswith("/VerificationCheck"):
            return Resp(200, {"status": "approved" if data["Code"] == "123456" else "pending"})
        return Resp(201, {"status": "pending"})

    monkeypatch.setattr(phone_otp.requests, "post", fake_post)
    client.post(reverse("webapp:signup"), _data())
    assert calls[0][0] == "https://verify.twilio.com/v2/Services/VA1/Verifications"
    assert calls[0][1] == {"To": "+919847554224", "Channel": "sms"} and calls[0][2] == ("AC1", "tok")
    client.post(reverse("webapp:signup_verify"), {"code": "654321"})
    assert not User.objects.filter(email="anu@spice.test").exists()
    client.post(reverse("webapp:signup_verify"), {"code": "123 456"})
    assert User.objects.get(email="anu@spice.test").phone_verified

    client.logout()
    # Twilio refusing the number shows a message instead of an error page
    monkeypatch.setattr(phone_otp.requests, "post", lambda *a, **k: Resp(400, {"message": "Invalid parameter"}))
    page = client.post(reverse("webapp:signup"), _data(email="b@spice.test", phone="+97455551234"),
                       follow=True).content.decode()
    assert "could not send a code" in page


def test_off_means_old_signup(client, settings):
    settings.PHONE_OTP_BACKEND = ""
    r = client.post(reverse("webapp:signup"), _data(phone=""))
    assert r.url == reverse("webapp:setup", kwargs={"step": "business"})
