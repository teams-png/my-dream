"""Excel downloads of reports open as real .xlsx workbooks with the expected rows."""
import io
import re
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.expenses.models import ExpenseCategory
from apps.expenses.services import record_expense
from apps.inventory.services import record_stock_movement
from apps.sales import services as sales
from apps.webapp import xlsx

pytestmark = pytest.mark.django_db
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _text(resp):
    assert resp.status_code == 200 and resp["Content-Type"] == XLSX, resp.status_code
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        assert "xl/workbook.xml" in z.namelist()
        return z.read("xl/worksheets/sheet1.xml").decode()


@pytest.fixture
def books(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="RICE", stock_price=Decimal("100"))
    record_stock_movement(company=tenant_a, product=base["product"], warehouse=base["warehouse"], quantity=10, reason="purchase")
    inv = sales.create_invoice(company=tenant_a, user=tenant_a_owner, customer=base["customer"], date=date.today(),
                               warehouse=base["warehouse"], lines=[{"product": base["product"], "quantity": 2, "unit_price": Decimal("150")}])
    cat = ExpenseCategory.objects.create(company=tenant_a, name="Rent")
    record_expense(company=tenant_a, user=tenant_a_owner, category=cat, date=date.today(), amount=Decimal("40"))
    client.force_login(tenant_a_owner)
    return {"client": client, "invoice": inv, "customer": base["customer"], "product": base["product"]}


def test_writer_escapes_and_never_writes_formulas():
    raw = xlsx.build([("A/B", [["=HYPERLINK(\"x\")", "<b>&", Decimal("1.50"), date(2026, 1, 2)]], 1)])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        assert "<f>" not in sheet and "&lt;b&gt;&amp;" in sheet and "<v>1.50</v>" in sheet
        assert 'name="A B"' in z.read("xl/workbook.xml").decode()


@pytest.mark.parametrize("name,args,expect", [
    ("acc_pl", [], "Net profit"), ("acc_bs", [], "Assets"), ("acc_tb", [], "Trial balance"),
    ("sales_invoice_list", [], "INV"), ("stock_home", [], "RICE"), ("receivables", [], "Outstanding"),
    ("budgets", [], "Rent"), ("expense_list", [], "Rent"),
])
def test_report_downloads(books, name, args, expect):
    sheet = _text(books["client"].get(reverse(f"webapp:{name}", args=args) + "?format=xlsx"))
    assert expect in sheet or re.search(expect, sheet)


def test_statement_and_ledger(books):
    sheet = _text(books["client"].get(reverse("webapp:customer_account", args=[books["customer"].id]) + "?format=xlsx"))
    assert books["invoice"].invoice_number in sheet and "<v>300.00</v>" in sheet
    from apps.accounting.models import Account
    account = Account.objects.for_company(books["invoice"].company).get(code="4000")
    assert "Sales" in _text(books["client"].get(reverse("webapp:acc_ledger", args=[account.id]) + "?period=all&format=xlsx"))


def test_buttons_are_shown(books):
    assert "format=xlsx" in books["client"].get(reverse("webapp:acc_pl")).content.decode()
    assert "format=xlsx" in books["client"].get(reverse("webapp:stock_home")).content.decode()
