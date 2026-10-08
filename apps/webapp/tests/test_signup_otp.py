"""Sign-up emails a code (or sends it by SMS); the account is made only after the code is typed."""
import re

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from apps.accounts import signup_otp
from apps.accounts.models import LoginAttempt, User
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db
VERIFY = reverse("webapp:signup_verify")


@pytest.fixture(autouse=True)
def otp_on(settings):
    call_command("seed_platform")
    settings.SIGNUP_OTP = "email"


def _data(**over):
    data = {"business_name": "Spice Garden", "business_type": "restaurant", "country": "India",
            "full_name": "Anu Thomas", "email": "anu@spice.test", "phone": "98475 54224",
            "password": "Tasty-Food-2026!", "accept_terms": "on", "website": ""}
    data.update(over)
    return data


def _code():
    return re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)


def test_helpers():
    assert signup_otp.normalize("98475 54224", "India") == "+919847554224"
    assert signup_otp.normalize("+91 98475-54224", "Qatar") == "+919847554224"
    assert signup_otp.normalize("0097455551234", "India") == "+97455551234"
    assert signup_otp.normalize("5555 1234", "Qatar") == "+97455551234"
    assert signup_otp.normalize("12", "Qatar") == "" and signup_otp.normalize("5555 1234", "Other") == ""
    assert signup_otp.masked("anu@spice.test") == "a••@spice.test"
    assert signup_otp.masked("+919847554224") == "+919•••••4224"


def test_email_code_then_account(client):
    page = client.get(reverse("webapp:signup")).content.decode()
    assert "We will email you a code" in page and "Phone (optional)" in page
    r = client.post(reverse("webapp:signup"), _data())
    assert r.url == VERIFY
    assert not User.objects.filter(email="anu@spice.test").exists()  # nothing is made before the code
    assert mail.outbox[-1].to == ["anu@spice.test"] and _code() in mail.outbox[-1].subject
    pending = client.session["pending_signup"]
    assert "password" not in pending and "Tasty-Food" not in str(pending)
    page = client.get(VERIFY).content.decode()
    assert "Check your email" in page and "a••@spice.test" in page and "Change email" in page

    code = _code()
    r = client.post(VERIFY, {"code": "000000" if code != "000000" else "111111"})
    assert r.url == VERIFY and not User.objects.filter(email="anu@spice.test").exists()
    r = client.post(VERIFY, {"code": code})
    assert r.url == reverse("webapp:setup", kwargs={"step": "business"})
    user = User.objects.get(email="anu@spice.test")
    assert user.email_verified and not user.phone_verified and user.check_password("Tasty-Food-2026!")
    assert Company.objects.get(name="Spice Garden").country == "India"
    assert "pending_signup" not in client.session


def test_code_expires(client):
    client.post(reverse("webapp:signup"), _data())
    s = client.session
    s["otp_made_at"] -= 11 * 60
    s.save()
    client.post(VERIFY, {"code": _code()})
    assert not User.objects.filter(email="anu@spice.test").exists()


def test_limits(client, settings):
    client.post(reverse("webapp:signup"), _data())
    client.post(VERIFY, {"action": "resend"})  # too soon: waits a minute
    assert len(mail.outbox) == 1 and LoginAttempt.objects.filter(identifier="otp-send:anu@spice.test").count() == 1
    for _ in range(6):  # five wrong codes, then a new code is needed
        client.post(VERIFY, {"code": "999999" if _code() != "999999" else "888888"})
    client.post(VERIFY, {"code": _code()})
    assert not User.objects.filter(email="anu@spice.test").exists()
    s = client.session
    s["otp_sent_at"] = 0
    s.save()
    client.post(VERIFY, {"action": "resend"})
    assert len(mail.outbox) == 2
    client.post(VERIFY, {"code": _code()})
    assert User.objects.filter(email="anu@spice.test").exists()

    client.logout()
    settings.SIGNUP_OTP_SENDS_PER_HOUR = 1
    client.post(reverse("webapp:signup"), _data(email="b@spice.test"))
    s = client.session
    s["otp_sent_at"] = 0
    s.save()
    page = client.post(VERIFY, {"action": "resend"}, follow=True).content.decode()
    assert "Too many codes" in page


def test_change_email_keeps_the_form(client):
    client.post(reverse("webapp:signup"), _data())
    page = client.get(reverse("webapp:signup") + "?edit=1").content.decode()
    assert "Spice Garden" in page and "anu@spice.test" in page and "Tasty-Food" not in page


def test_no_mail_server_means_no_code(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = ""
    r = client.post(reverse("webapp:signup"), _data())
    assert r.url == reverse("webapp:setup", kwargs={"step": "business"})  # a code could never arrive


def test_email_that_cannot_be_sent(client, settings):
    settings.EMAIL_BACKEND = "apps.platform_admin.tests.test_help_chat.BrokenEmailBackend"
    page = client.post(reverse("webapp:signup"), _data(), follow=True).content.decode()
    assert "could not send the email" in page and not User.objects.exists()


def test_off_means_old_signup(client, settings):
    settings.SIGNUP_OTP = ""
    r = client.post(reverse("webapp:signup"), _data(phone=""))
    assert r.url == reverse("webapp:setup", kwargs={"step": "business"})


def test_sms_with_twilio(client, settings, monkeypatch):
    settings.SIGNUP_OTP = "sms"
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

    monkeypatch.setattr(signup_otp.requests, "post", fake_post)
    assert "Mobile number" in client.get(reverse("webapp:signup")).content.decode()
    assert "valid mobile number" in client.post(reverse("webapp:signup"), _data(phone="123")).content.decode()
    client.post(reverse("webapp:signup"), _data())
    assert calls[0][0] == "https://verify.twilio.com/v2/Services/VA1/Verifications"
    assert calls[0][1] == {"To": "+919847554224", "Channel": "sms"} and calls[0][2] == ("AC1", "tok")
    assert "+919•••••4224" in client.get(VERIFY).content.decode()
    client.post(VERIFY, {"code": "654321"})
    assert not User.objects.filter(email="anu@spice.test").exists()
    client.post(VERIFY, {"code": "123 456"})
    user = User.objects.get(email="anu@spice.test")
    assert user.phone_verified and user.phone == "+919847554224"

    client.logout()
    page = client.post(reverse("webapp:signup"), _data(email="c@spice.test")).content.decode()
    assert "mobile number already exists" in page
    monkeypatch.setattr(signup_otp.requests, "post", lambda *a, **k: Resp(400, {"message": "Invalid parameter"}))
    page = client.post(reverse("webapp:signup"), _data(email="b@spice.test", phone="+97455551234"),
                       follow=True).content.decode()
    assert "could not send a code" in page
