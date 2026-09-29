"""
Tenant isolation tests (Phase 0 Section 3 / master brief Section 38).

These are the single most important tests in the whole suite. Every one
of them follows the same shape: create data under tenant A, then prove
tenant B's authenticated user cannot see, fetch, or write it — neither
through the ORM manager directly, nor through the API (including by
guessing a valid primary key — the IDOR case).
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


class TestORMLevelIsolation:
    """Guards the manager itself, independent of any view bug."""

    def test_for_company_excludes_other_tenants(self, tenant_a, tenant_b):
        from apps.customers.models import Customer

        Customer.objects.create(company=tenant_a, name="A's Customer")
        Customer.objects.create(company=tenant_b, name="B's Customer")

        a_customers = list(Customer.objects.for_company(tenant_a))
        b_customers = list(Customer.objects.for_company(tenant_b))

        assert [c.name for c in a_customers] == ["A's Customer"]
        assert [c.name for c in b_customers] == ["B's Customer"]

    def test_chart_of_accounts_is_not_shared_across_tenants(self, tenant_a, tenant_b):
        from apps.accounting.models import Account

        a_accounts = set(Account.objects.for_company(tenant_a).values_list("code", flat=True))
        b_accounts = set(Account.objects.for_company(tenant_b).values_list("code", flat=True))

        # Same default chart of accounts codes, but genuinely different rows.
        assert a_accounts == b_accounts  # same codes seeded for every company
        a_ids = set(Account.objects.for_company(tenant_a).values_list("id", flat=True))
        b_ids = set(Account.objects.for_company(tenant_b).values_list("id", flat=True))
        assert a_ids.isdisjoint(b_ids)  # but zero row overlap


class TestAPILevelIsolation:
    """The realistic attack surface: an authenticated user of tenant B
    trying to see or touch tenant A's data through the HTTP API."""

    def test_customer_list_never_shows_other_tenants_data(
        self, as_tenant_a_owner, as_tenant_b_owner, tenant_a, tenant_b
    ):
        from apps.customers.models import Customer

        Customer.objects.create(company=tenant_a, name="A's Customer")
        Customer.objects.create(company=tenant_b, name="B's Customer")

        resp_a = as_tenant_a_owner.get("/api/customers/")
        resp_b = as_tenant_b_owner.get("/api/customers/")
        assert resp_a.status_code == 200 and resp_b.status_code == 200

        # DefaultRouter + ModelViewSet: unpaginated unless PAGE_SIZE is set
        # in settings, in which case DRF wraps the list in {"results": [...]}.
        payload_a, payload_b = resp_a.json(), resp_b.json()
        list_a = payload_a.get("results", payload_a) if isinstance(payload_a, dict) else payload_a
        list_b = payload_b.get("results", payload_b) if isinstance(payload_b, dict) else payload_b

        assert {c["name"] for c in list_a} == {"A's Customer"}
        assert {c["name"] for c in list_b} == {"B's Customer"}

    def test_idor_cannot_fetch_another_tenants_customer_by_id(
        self, as_tenant_a_owner, as_tenant_b_owner, tenant_a
    ):
        from apps.customers.models import Customer

        a_customer = Customer.objects.create(company=tenant_a, name="A's Private Customer")

        # Tenant A can fetch their own record.
        own_resp = as_tenant_a_owner.get(f"/api/customers/{a_customer.id}/")
        assert own_resp.status_code == 200

        # Tenant B guessing/incrementing the same primary key must NOT succeed.
        idor_resp = as_tenant_b_owner.get(f"/api/customers/{a_customer.id}/")
        assert idor_resp.status_code == 404

    def test_cannot_create_invoice_using_another_tenants_customer(
        self, as_tenant_a_owner, tenant_a, tenant_b, sales_fixtures_factory
    ):
        """
        The IDOR guard in sales.views.SalesInvoiceViewSet.create(): a
        PrimaryKeyRelatedField only proves the id exists SOMEWHERE, not
        that it belongs to the caller's tenant. This is exactly the class
        of bug Section 38 calls out by name.
        """
        fx_a = sales_fixtures_factory(tenant_a, sku="A-SKU")
        fx_b = sales_fixtures_factory(tenant_b, sku="B-SKU")

        payload = {
            "customer": fx_b["customer"].id,       # <-- belongs to tenant B
            "warehouse": fx_a["warehouse"].id,
            "date": "2026-01-15",
            "lines": [{"product": fx_a["product"].id, "quantity": "1", "unit_price": "100.00"}],
        }
        resp = as_tenant_a_owner.post("/api/sales/invoices/", payload, format="json")
        assert resp.status_code == 400
        assert "customer" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()

    def test_cannot_create_invoice_using_another_tenants_product(
        self, as_tenant_a_owner, tenant_a, tenant_b, sales_fixtures_factory
    ):
        fx_a = sales_fixtures_factory(tenant_a, sku="A-SKU-2")
        fx_b = sales_fixtures_factory(tenant_b, sku="B-SKU-2")

        payload = {
            "customer": fx_a["customer"].id,
            "warehouse": fx_a["warehouse"].id,
            "date": "2026-01-15",
            "lines": [{"product": fx_b["product"].id, "quantity": "1", "unit_price": "100.00"}],  # <-- tenant B's product
        }
        resp = as_tenant_a_owner.post("/api/sales/invoices/", payload, format="json")
        assert resp.status_code == 400

    def test_reports_only_reflect_the_callers_own_tenant(
        self, as_tenant_a_owner, tenant_a, tenant_b, sales_fixtures_factory, tenant_a_owner
    ):
        """A P&L/trial-balance leak would be a severe cross-tenant financial
        data breach — verify the reports endpoint is company-scoped."""
        from apps.sales.services import create_invoice

        fx_a = sales_fixtures_factory(tenant_a, sku="REPORT-A")
        create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=fx_a["customer"],
            date="2026-01-10", warehouse=fx_a["warehouse"],
            lines=[{"product": fx_a["product"], "quantity": Decimal("2"), "unit_price": Decimal("100.00")}],
        )

        resp = as_tenant_a_owner.get("/api/reports/trial-balance/")
        assert resp.status_code == 200

        # Every account row returned must genuinely belong to tenant A —
        # and Tenant A's own Accounts Receivable must show the invoice total.
        from apps.accounting.models import Account
        a_account_ids = set(Account.objects.for_company(tenant_a).values_list("id", flat=True))
        rows = resp.json()["rows"]
        for row in rows:
            assert row["account"]["id"] in a_account_ids

        ar_row = next(r for r in rows if r["account"]["code"] == "1100")
        assert Decimal(ar_row["balance"]) == Decimal("200.00")
