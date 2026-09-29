import time

import pytest
from django.urls import reverse

from apps.accounts import twofactor
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="owner@shop.test", email="owner@shop.test", password="Strong-Pass-123")


def test_totp_matches_rfc6238_reference():
    # RFC 6238 appendix B, SHA-1 secret "12345678901234567890", 8 digits -> last 6 digits
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert twofactor.current_code(secret, at=59) == "287082"
    assert twofactor.current_code(secret, at=1111111109) == "081804"


def _enable(user):
    secret = twofactor.start_setup(user)
    codes = twofactor.confirm_setup(user, twofactor.current_code(secret, at=time.time() - 30))
    assert codes and len(codes) == 8
    return secret, codes


def test_web_login_requires_code_when_enabled(client, user):
    secret, codes = _enable(user)
    resp = client.post(reverse("webapp:login"), {"username": "owner@shop.test", "password": "Strong-Pass-123"})
    assert resp.url == reverse("webapp:login_2fa")
    assert "_auth_user_id" not in client.session  # not logged in yet
    bad = client.post(reverse("webapp:login_2fa"), {"code": "000000"})
    assert bad.status_code == 200 and "_auth_user_id" not in client.session
    ok = client.post(reverse("webapp:login_2fa"), {"code": twofactor.current_code(secret)})
    assert ok.status_code == 302 and client.session["_auth_user_id"] == str(user.pk)


def test_code_cannot_be_replayed_and_recovery_codes_work_once(user):
    secret, codes = _enable(user)
    code = twofactor.current_code(secret)
    assert twofactor.verify(user, code) is True
    assert twofactor.verify(user, code) is False
    assert twofactor.verify(user, codes[0]) is True
    assert twofactor.verify(user, codes[0]) is False
    assert twofactor.remaining_recovery_codes(user) == 7


def test_api_login_requires_otp(client, user):
    secret, _ = _enable(user)
    url = "/api/accounts/login/"
    resp = client.post(url, {"username": "owner@shop.test", "password": "Strong-Pass-123"}, content_type="application/json")
    assert resp.status_code == 401 and resp.json()["two_factor_required"] is True
    resp = client.post(url, {"username": "owner@shop.test", "password": "Strong-Pass-123", "otp": twofactor.current_code(secret)}, content_type="application/json")
    assert resp.status_code == 200 and "access" in resp.json()


def test_security_page_setup_and_disable(client, user):
    client.force_login(user)
    url = reverse("webapp:security_settings")
    client.post(url, {"action": "start"})
    page = client.get(url)
    assert b"<svg" in page.content and page.context["setup_secret"]
    secret = page.context["setup_secret"]
    done = client.post(url, {"action": "confirm", "code": twofactor.current_code(secret)})
    assert len(done.context["recovery_codes"]) == 8 and twofactor.is_enabled(user)
    client.post(url, {"action": "disable", "password": "wrong", "code": twofactor.current_code(secret, at=time.time() + 30)})
    assert twofactor.is_enabled(user)
    client.post(url, {"action": "disable", "password": "Strong-Pass-123", "code": twofactor.current_code(secret, at=time.time() + 30)})
    assert not twofactor.is_enabled(user)
