"""Phase 1 Section 38: Registration, Login."""
import pytest

pytestmark = pytest.mark.django_db


def test_register_creates_user(api_client):
    resp = api_client.post("/api/accounts/register/", {
        "username": "newowner@example.com", "email": "newowner@example.com",
        "password": "StrongPass123!", "phone": "+97400000000",
    })
    assert resp.status_code == 201, resp.data


def test_login_returns_access_and_refresh_tokens(api_client):
    api_client.post("/api/accounts/register/", {
        "username": "loginuser@example.com", "email": "loginuser@example.com",
        "password": "StrongPass123!",
    })
    resp = api_client.post("/api/accounts/login/", {
        "username": "loginuser@example.com", "password": "StrongPass123!",
    })
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data


def test_login_wrong_password_fails(api_client):
    api_client.post("/api/accounts/register/", {
        "username": "wrongpass@example.com", "email": "wrongpass@example.com",
        "password": "StrongPass123!",
    })
    resp = api_client.post("/api/accounts/login/", {
        "username": "wrongpass@example.com", "password": "not-the-password",
    })
    assert resp.status_code == 401


def test_repeated_failed_logins_lock_the_account(api_client):
    """Phase 18 Section 27 'Login attempt protection' — 5 failures locks out the 6th attempt."""
    api_client.post("/api/accounts/register/", {
        "username": "lockout@example.com", "email": "lockout@example.com",
        "password": "StrongPass123!",
    })
    for _ in range(5):
        resp = api_client.post("/api/accounts/login/", {
            "username": "lockout@example.com", "password": "wrong",
        })
        assert resp.status_code == 401

    resp = api_client.post("/api/accounts/login/", {
        "username": "lockout@example.com", "password": "StrongPass123!",  # correct password now
    })
    assert resp.status_code == 423, "6th attempt should be locked out even with the correct password"
