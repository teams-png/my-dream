"""
Phase 1 Section 38: "Especially test: USER A from TENANT A must NEVER
access TENANT B data." This file is that test, across every layer where
leakage could happen: list, retrieve-by-id, and update-by-id.
"""
import pytest

pytestmark = pytest.mark.django_db


def test_user_a_cannot_list_tenant_b_customers(make_company, with_active_company):
    company_a, owner_a = make_company("textile", owner_email="owner-a@example.com")
    company_b, owner_b = make_company("textile", owner_email="owner-b@example.com")

    client_b = with_active_company(owner_b, company_b)
    client_b.post("/api/customers/", {"name": "Company B's Customer", "phone": "1111111111"})

    client_a = with_active_company(owner_a, company_a)
    resp = client_a.get("/api/customers/")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.data.get("results", resp.data)]
    assert "Company B's Customer" not in names


def test_user_a_cannot_retrieve_tenant_b_customer_by_id(make_company, with_active_company):
    """The sharper version of the list test — guessing/enumerating IDs must not work either."""
    company_a, owner_a = make_company("textile", owner_email="owner-a2@example.com")
    company_b, owner_b = make_company("textile", owner_email="owner-b2@example.com")

    client_b = with_active_company(owner_b, company_b)
    created = client_b.post("/api/customers/", {"name": "B Secret Customer", "phone": "2222222222"})
    b_customer_id = created.data["id"]

    client_a = with_active_company(owner_a, company_a)
    resp = client_a.get(f"/api/customers/{b_customer_id}/")
    assert resp.status_code == 404, "Company A must get 404, not the other tenant's data, not a 403 that confirms existence"


def test_user_a_cannot_update_tenant_b_customer_by_id(make_company, with_active_company):
    company_a, owner_a = make_company("textile", owner_email="owner-a3@example.com")
    company_b, owner_b = make_company("textile", owner_email="owner-b3@example.com")

    client_b = with_active_company(owner_b, company_b)
    created = client_b.post("/api/customers/", {"name": "B Original Name", "phone": "3333333333"})
    b_customer_id = created.data["id"]

    client_a = with_active_company(owner_a, company_a)
    resp = client_a.patch(f"/api/customers/{b_customer_id}/", {"name": "Hijacked By A"})
    assert resp.status_code == 404

    # Confirm the record on B's side is untouched.
    resp_b = client_b.get(f"/api/customers/{b_customer_id}/")
    assert resp_b.data["name"] == "B Original Name"


def test_user_not_a_member_of_any_company_has_no_active_company(make_company, auth_client):
    """A brand-new user with no CompanyMembership at all — must not silently see someone else's company."""
    company_a, owner_a = make_company("textile", owner_email="owner-a4@example.com")

    from tests.conftest import make_user
    outsider = make_user("outsider@example.com")
    client = auth_client(outsider)

    resp = client.get("/api/tenants/active-company/")
    assert resp.status_code == 404
