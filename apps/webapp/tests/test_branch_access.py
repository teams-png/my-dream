"""Staff assigned to a branch sell from, and see stock and bills of, that branch only."""
import json
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.accounting.services import seed_chart_of_accounts
from apps.inventory import branch_access
from apps.inventory.models import Warehouse
from apps.inventory.services import record_stock_movement
from apps.sales.models import SalesInvoice
from apps.tenants.models import CompanyMembership, Role, RolePermission

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    data = sales_fixtures_factory(tenant_a, sku="TEA")
    main = data["warehouse"]
    Warehouse.objects.filter(id=main.id).update(is_default=True, name="Doha Main")
    mall = Warehouse.objects.create(company=tenant_a, name="Mall Kiosk", is_active=True)
    for wh, qty in ((main, 20), (mall, 5)):
        record_stock_movement(company=tenant_a, product=data["product"], warehouse=wh, quantity=Decimal(qty), reason="purchase")
    owner_role = Role.objects.get(company=tenant_a, name="Owner")
    cashier = Role.objects.create(company=tenant_a, name="Cashier")
    RolePermission.objects.bulk_create([RolePermission(role=cashier, permission_id=pid)
                                        for pid in owner_role.permissions.values_list("permission_id", flat=True)])
    user = get_user_model().objects.create_user(username="kiosk", email="kiosk@t.qa", password="Pass-12345!")
    membership = CompanyMembership.objects.create(user=user, company=tenant_a, role=cashier)
    membership.warehouses.set([mall])
    return {**data, "company": tenant_a, "owner": tenant_a_owner, "main": main, "mall": mall, "user": user,
            "membership": membership}


def _sale(shop, warehouse_id=None):
    return {"client_id": str(uuid.uuid4()), "payment_method": "cash", "created_at": timezone.now().isoformat(),
            "total": "100.00", "warehouse_id": warehouse_id,
            "lines": [{"product_id": shop["product"].id, "quantity": 1, "unit_price": "100.00", "name": "Tea"}]}


def test_cashier_sells_from_own_branch_even_if_another_is_requested(client, shop):
    client.force_login(shop["user"])
    resp = client.post(reverse("webapp:pos_checkout"), json.dumps(_sale(shop, shop["main"].id)), content_type="application/json")
    assert resp.status_code == 200, resp.content
    invoice = SalesInvoice.objects.get(company=shop["company"], invoice_number=resp.json()["invoice_number"])
    assert invoice.warehouse_id == shop["mall"].id
    page = client.get(reverse("webapp:pos"))
    assert [b.id for b in page.context["branches"]] == [shop["mall"].id]
    assert branch_access.allowed() is None  # nothing leaks past the request


def test_owner_is_never_restricted(client, shop):
    owner_membership = CompanyMembership.objects.get(user=shop["owner"], company=shop["company"])
    owner_membership.warehouses.set([shop["mall"]])
    client.force_login(shop["owner"])
    resp = client.post(reverse("webapp:pos_checkout"), json.dumps(_sale(shop)), content_type="application/json")
    invoice = SalesInvoice.objects.get(company=shop["company"], invoice_number=resp.json()["invoice_number"])
    assert invoice.warehouse_id == shop["main"].id
    assert len(client.get(reverse("webapp:stock_home")).context["warehouses"]) == 2


def test_stock_and_bill_lists_show_own_branch_only(client, shop):
    client.force_login(shop["owner"])
    client.post(reverse("webapp:pos_checkout"), json.dumps(_sale(shop)), content_type="application/json")  # main branch
    client.force_login(shop["user"])
    client.post(reverse("webapp:pos_checkout"), json.dumps(_sale(shop)), content_type="application/json")  # mall
    stock = client.get(reverse("webapp:stock_home"))
    assert [w.id for w in stock.context["warehouses"]] == [shop["mall"].id]
    row = stock.context["page"].object_list[0]
    assert row["total"] == Decimal("4")  # 5 at the kiosk less the one sold; main branch stock hidden
    bills = client.get(reverse("webapp:sales_invoice_list")).context["page"].object_list
    assert [b.warehouse_id for b in bills] == [shop["mall"].id]
    transfer = client.get(reverse("webapp:stock_transfer"))
    assert [w.id for w in transfer.context["warehouses"]] == [shop["mall"].id]
    assert len(transfer.context["targets"]) == 2


def test_owner_assigns_branches_from_team_page(client, shop):
    client.force_login(shop["owner"])
    url = reverse("webapp:staff_role_change", args=[shop["membership"].id])
    page = client.get(url).content.decode()
    assert "Mall Kiosk" in page and "Doha Main" in page
    client.post(url, {"role": shop["membership"].role_id, "branches": [shop["main"].id, shop["mall"].id]})
    assert set(shop["membership"].warehouses.values_list("id", flat=True)) == {shop["main"].id, shop["mall"].id}
    client.post(url, {"role": shop["membership"].role_id})
    assert not shop["membership"].warehouses.exists()
    assert "All branches" in client.get(reverse("webapp:staff_members_list")).content.decode()
