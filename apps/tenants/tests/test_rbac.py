"""
RBAC tests (master brief Section 7):
  - Owner: full control, including subscription and role management.
  - Accountant: full accounting/sales/purchases, but NOT subscription
    changes, NOT deleting the Owner, NOT sensitive settings.
  - Staff: create sales/customers, view products — NOT P&L/Balance Sheet,
    NOT company financial settings, NOT subscription, NOT user management.

These are deliberately API-level (not just "does the Role have the
Permission row" unit checks) — Section 7's own words are "a Staff user
hitting a protected endpoint directly must be blocked", i.e. the HTTP
layer is the thing under test, not just the data model.
"""
import pytest

pytestmark = pytest.mark.django_db


class TestStaffRestrictions:
    def test_staff_cannot_view_reports(self, tenant_a, member_factory):
        from conftest import jwt_client

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        resp = client.get("/api/reports/trial-balance/")
        assert resp.status_code == 403

    def test_staff_cannot_manage_roles_or_members(self, tenant_a, member_factory):
        from conftest import jwt_client

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        assert client.get("/api/tenants/roles/").status_code == 403
        assert client.get("/api/tenants/members/").status_code == 403

    def test_staff_can_view_products_and_create_customers(
        self, tenant_a, member_factory, sales_fixtures_factory
    ):
        from conftest import jwt_client

        sales_fixtures_factory(tenant_a)  # seeds a product etc.
        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        assert client.get("/api/inventory/products/").status_code == 200
        create_resp = client.post("/api/customers/", {"name": "New Walk-in"}, format="json")
        assert create_resp.status_code == 201

    def test_staff_can_create_invoice_but_default_permission_map_has_no_manage_stock(
        self, tenant_a, member_factory, sales_fixtures_factory
    ):
        """
        Sanity-check on the seeded default map itself (tenants.services.
        ROLE_PERMISSION_MAP): Staff gets sales.create_invoice — matches
        Section 7's "Create sales" — but NOT inventory.manage_products
        (Staff shouldn't be able to edit cost prices / delete products).
        """
        from apps.tenants.models import Role

        staff_role = Role.objects.get(company=tenant_a, name="Staff")
        codes = set(staff_role.permissions.values_list("permission__code", flat=True))
        assert "sales.create_invoice" in codes
        assert "inventory.manage_products" not in codes


class TestAccountantRestrictions:
    def test_accountant_cannot_manage_roles(self, tenant_a, member_factory):
        """Section 7: Accountant must NOT be able to change subscription,
        delete the Owner, or touch sensitive settings — role/member
        management is grouped under the same 'sensitive settings' gate."""
        from conftest import jwt_client

        accountant = member_factory(tenant_a, "Accountant")
        client = jwt_client(accountant)

        assert client.get("/api/tenants/roles/").status_code == 403
        assert client.get("/api/tenants/members/").status_code == 403

    def test_accountant_can_view_and_post_accounting_reports(self, tenant_a, member_factory):
        from conftest import jwt_client

        accountant = member_factory(tenant_a, "Accountant")
        client = jwt_client(accountant)

        assert client.get("/api/reports/trial-balance/").status_code == 200
        assert client.get("/api/reports/profit-and-loss/").status_code == 200
        assert client.get("/api/reports/balance-sheet/").status_code == 200

    def test_accountant_permission_set_excludes_role_management(self, tenant_a):
        from apps.tenants.models import Role

        accountant_role = Role.objects.get(company=tenant_a, name="Accountant")
        codes = set(accountant_role.permissions.values_list("permission__code", flat=True))
        assert "tenants.manage_roles" not in codes
        assert "tenants.manage_members" not in codes
        assert "accounting.view_reports" in codes


class TestOwnerFullAccess:
    def test_owner_has_every_permission_in_the_catalog(self, tenant_a):
        from apps.tenants.models import Role, Permission

        owner_role = Role.objects.get(company=tenant_a, name="Owner")
        owner_codes = set(owner_role.permissions.values_list("permission__code", flat=True))
        all_codes = set(Permission.objects.values_list("code", flat=True))
        assert owner_codes == all_codes

    def test_owner_can_manage_roles_and_reports(self, as_tenant_a_owner):
        assert as_tenant_a_owner.get("/api/tenants/roles/").status_code == 200
        assert as_tenant_a_owner.get("/api/reports/trial-balance/").status_code == 200

    def test_owner_can_customize_a_custom_roles_permissions(self, as_tenant_a_owner, tenant_a):
        """Section 7: 'Create a permission system so the Owner can
        customize permissions.' System roles are protected (see
        test_system_roles_cannot_be_edited below) — this checks the
        sanctioned path: a brand-new custom role."""
        create_resp = as_tenant_a_owner.post(
            "/api/tenants/roles/", {"name": "Cashier"}, format="json"
        )
        assert create_resp.status_code == 201
        role_id = create_resp.json()["id"]

        set_perms_resp = as_tenant_a_owner.post(
            f"/api/tenants/roles/{role_id}/set_permissions/",
            {"permission_codes": ["sales.create_invoice", "sales.view_invoice"]},
            format="json",
        )
        assert set_perms_resp.status_code == 200
        assert set(set_perms_resp.json()["permission_codes"]) == {
            "sales.create_invoice", "sales.view_invoice",
        }

    def test_system_roles_cannot_be_edited_or_deleted(self, as_tenant_a_owner, tenant_a):
        from apps.tenants.models import Role

        owner_role = Role.objects.get(company=tenant_a, name="Owner")

        set_perms_resp = as_tenant_a_owner.post(
            f"/api/tenants/roles/{owner_role.id}/set_permissions/",
            {"permission_codes": ["sales.view_invoice"]},
            format="json",
        )
        assert set_perms_resp.status_code == 400

        delete_resp = as_tenant_a_owner.delete(f"/api/tenants/roles/{owner_role.id}/")
        assert delete_resp.status_code == 400
