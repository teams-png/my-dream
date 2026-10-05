"""Owner, Accountant and Staff see and open different pages."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.tenants.models import CompanyMembership, Role
from apps.webapp.role_access import PAGE_PERMISSIONS, required_permission

pytestmark = pytest.mark.django_db

OWNER_ONLY = ["company_settings", "staff_members_list", "role_list", "backups", "branch_list", "online_payment_settings",
              "tax_currency", "company_audit_log"]
MONEY = ["analytics", "reports", "acc_pl", "expense_list", "supplier_list", "purchase_list", "finance_home", "bank_home"]
EVERYONE = ["dashboard", "pos", "customer_list", "sales_invoice_list", "product_list", "help", "notification_list"]


def _member(company, role_name, email):
    user = User.objects.create_user(username=email, email=email, password="Member-Pass-2026")
    CompanyMembership.objects.create(user=user, company=company, role=Role.objects.get(company=company, name=role_name))
    c = Client()
    c.force_login(user)
    return c


def _status(c, name):
    return c.get(reverse(f"webapp:{name}")).status_code


def test_staff_accountant_owner_differ(tenant_a, tenant_a_owner):
    owner = Client()
    owner.force_login(tenant_a_owner)
    staff = _member(tenant_a, "Staff", "cashier@abc.qa")
    accountant = _member(tenant_a, "Accountant", "books@abc.qa")

    for name in OWNER_ONLY + MONEY + EVERYONE:
        assert _status(owner, name) != 403, name
    for name in OWNER_ONLY + MONEY:
        assert _status(staff, name) == 403, name
    for name in EVERYONE:
        assert _status(staff, name) != 403, name
    for name in OWNER_ONLY:
        assert _status(accountant, name) == 403, name
    for name in MONEY + EVERYONE:
        assert _status(accountant, name) != 403, name

    page = staff.get(reverse("webapp:company_settings"))
    assert "Your role can" in page.content.decode() and "Staff" in page.content.decode()


def test_sidebar_and_dashboard_follow_the_role(tenant_a, tenant_a_owner):
    owner = Client()
    owner.force_login(tenant_a_owner)
    staff = _member(tenant_a, "Staff", "cashier@abc.qa")
    own = owner.get(reverse("webapp:dashboard")).content.decode()
    mine = staff.get(reverse("webapp:dashboard")).content.decode()
    for name in ("company_settings", "analytics", "expense_list", "supplier_list", "staff_members_list", "backups"):
        href = f'href="{reverse(f"webapp:{name}")}"'
        assert href in own, name
        assert href not in mine, name
    assert f'href="{reverse("webapp:billing")}"' in own and f'href="{reverse("webapp:billing")}"' not in mine
    assert f'href="{reverse("webapp:pos")}"' in mine and f'href="{reverse("webapp:customer_list")}"' in mine
    assert "This month&#x27;s revenue" not in mine and "revenue" in own


def test_owner_can_give_staff_more(tenant_a, tenant_a_owner):
    from apps.tenants.models import Permission, RolePermission
    staff = _member(tenant_a, "Staff", "cashier@abc.qa")
    assert _status(staff, "analytics") == 403
    role = Role.objects.get(company=tenant_a, name="Staff")
    RolePermission.objects.create(role=role, permission=Permission.objects.get(code="reports.view"))
    assert _status(staff, "analytics") != 403


def test_every_mapped_page_exists_and_reports_are_guarded():
    from apps.webapp import urls
    names = {p.name for p in urls.urlpatterns if p.name}
    assert set(PAGE_PERMISSIONS) <= names, set(PAGE_PERMISSIONS) - names
    assert required_permission("gym_reports") == "reports.view"
    assert required_permission("pos") is None
