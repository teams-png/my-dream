"""
Registration flow tests (master brief Section 4: register -> pick
business type + plan -> create company -> become Owner -> dashboard).

Phase 21: POST /api/tenants/companies/ (wired to apps.tenants.services.
create_company_with_owner) closes the gap flagged when this file was
first written in Phase 20 — company creation is now reachable over HTTP,
not just from Python/the admin.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class TestUserRegistrationAndLogin:
    def test_register_creates_a_user(self, api_client):
        resp = api_client.post(
            "/api/accounts/register/",
            {"email": "owner@newbiz.com", "username": "owner@newbiz.com", "password": "Str0ng-Pass-987"},
            format="json",
        )
        assert resp.status_code == 201
        from apps.accounts.models import User
        assert User.objects.filter(email="owner@newbiz.com").exists()

    def test_weak_password_is_rejected(self, api_client):
        resp = api_client.post(
            "/api/accounts/register/",
            {"email": "weak@newbiz.com", "username": "weak@newbiz.com", "password": "123"},
            format="json",
        )
        assert resp.status_code == 400

    def test_login_returns_jwt_tokens(self, api_client, user_factory):
        user_factory(email="login@example.com", password="Str0ng-Pass-987")
        resp = api_client.post(
            "/api/accounts/login/",
            {"username": "login@example.com", "password": "Str0ng-Pass-987"},
            format="json",
        )
        assert resp.status_code == 200
        assert "access" in resp.json() and "refresh" in resp.json()

    def test_me_endpoint_requires_authentication(self, api_client):
        assert api_client.get("/api/accounts/me/").status_code == 401


class TestFullRegistrationToOwnerFlow:
    def test_registered_user_becomes_owner_of_their_new_company(
        self, api_client, business_type, starter_plan
    ):
        """
        End-to-end simulation of Section 4's flow: register -> (business
        type + plan already chosen, business_type/starter_plan fixtures
        stand in for that UI step) -> create company -> become Owner ->
        reach an authenticated, company-scoped endpoint (the "dashboard").
        """
        from apps.tenants.services import create_company_with_owner

        register_resp = api_client.post(
            "/api/accounts/register/",
            {"email": "founder@newbiz.com", "username": "founder@newbiz.com", "password": "Str0ng-Pass-987"},
            format="json",
        )
        assert register_resp.status_code == 201

        login_resp = api_client.post(
            "/api/accounts/login/",
            {"username": "founder@newbiz.com", "password": "Str0ng-Pass-987"},
            format="json",
        )
        access_token = login_resp.json()["access"]

        from apps.accounts.models import User
        founder = User.objects.get(email="founder@newbiz.com")

        authed_client = APIClient()
        authed_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        # POST /api/tenants/companies/ — Section 4's "create business" step.
        register_company_resp = authed_client.post(
            "/api/tenants/companies/",
            {"name": "New Biz Textiles", "slug": "new-biz-textiles", "business_type": business_type.code},
            format="json",
        )
        assert register_company_resp.status_code == 201
        company_id = register_company_resp.json()["id"]

        me_resp = authed_client.get("/api/accounts/me/")
        assert me_resp.status_code == 200

        active_company_resp = authed_client.get("/api/tenants/active-company/")
        assert active_company_resp.status_code == 200
        assert active_company_resp.json()["id"] == company_id

        from apps.tenants.models import CompanyMembership
        membership = CompanyMembership.objects.get(user=founder, company_id=company_id)
        assert membership.role.name == "Owner"

        # Owner reaching a real "dashboard" data endpoint end-to-end.
        reports_resp = authed_client.get("/api/reports/trial-balance/")
        assert reports_resp.status_code == 200

    def test_cannot_register_a_company_with_a_duplicate_slug(self, api_client, business_type, user_factory):
        from apps.tenants.services import create_company_with_owner

        user_factory(email="dup@newbiz.com", password="Str0ng-Pass-987")
        create_company_with_owner(
            user=__import__("apps.accounts.models", fromlist=["User"]).User.objects.get(email="dup@newbiz.com"),
            name="Existing Co", slug="taken-slug", business_type=business_type,
        )

        login_resp = api_client.post(
            "/api/accounts/login/",
            {"username": "dup@newbiz.com", "password": "Str0ng-Pass-987"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.json()['access']}")

        resp = client.post(
            "/api/tenants/companies/",
            {"name": "Second Co", "slug": "taken-slug", "business_type": business_type.code},
            format="json",
        )
        assert resp.status_code == 400
