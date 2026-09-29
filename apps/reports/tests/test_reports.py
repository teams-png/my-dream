"""
Phase 25: every one of these endpoints was either missing its
apps.reports.services function entirely, calling one under the wrong
name, or getting back a dict shaped differently than the view expected —
and `pytest` stayed green through all of it because nothing exercised
them (see PHASE24_NOTES.md, "Still open"). These tests hit each report
through the real API (same as the rest of the suite), with real
invoices/purchases/expenses/payments behind them, specifically so that
kind of reassembly-mismatch bug fails loudly next time.
"""
from decimal import Decimal

import pytest

from apps.accounting.services import post_journal_entry
from apps.expenses.models import Expense, ExpenseCategory
from apps.expenses.services import record_expense
from apps.purchases.models import Purchase
from apps.purchases.services import create_purchase
from apps.sales.services import create_invoice, record_customer_payment
from apps.suppliers.models import Supplier


@pytest.fixture
def supplier(tenant_a):
    return Supplier.objects.create(company=tenant_a, name="Acme Supplies")


@pytest.fixture
def expense_category(tenant_a):
    return ExpenseCategory.objects.create(company=tenant_a, name="Rent")


@pytest.fixture
def invoice(tenant_a, tenant_a_owner, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a)
    return create_invoice(
        company=tenant_a, user=tenant_a_owner, customer=f["customer"], date="2026-01-15",
        lines=[{"product": f["product"], "quantity": Decimal("2"), "unit_price": Decimal("100.00")}],
        warehouse=f["warehouse"], tax_rate=Decimal("0.05"),
    )


@pytest.fixture
def purchase(tenant_a, tenant_a_owner, sales_fixtures_factory, supplier):
    f = sales_fixtures_factory(tenant_a, sku="SKU-PUR")
    return create_purchase(
        company=tenant_a, user=tenant_a_owner, supplier=supplier, date="2026-01-10",
        lines=[{"product": f["product"], "quantity": Decimal("5"), "unit_cost": Decimal("40.00")}],
        warehouse=f["warehouse"], tax_rate=Decimal("0.05"),
    )


@pytest.mark.django_db
class TestSalesReport:
    def test_totals_and_by_status(self, as_tenant_a_owner, invoice):
        resp = as_tenant_a_owner.get("/api/reports/sales/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["invoice_count"] == 1
        assert Decimal(str(data["total"])) == invoice.total
        assert any(row["status"] == "unpaid" for row in data["by_status"])

    def test_customer_id_filter_excludes_other_customers(self, as_tenant_a_owner, invoice, tenant_a, sales_fixtures_factory):
        other = sales_fixtures_factory(tenant_a, sku="SKU-OTHER")["customer"]
        resp = as_tenant_a_owner.get(f"/api/reports/sales/?customer_id={other.id}")
        assert resp.status_code == 200
        assert resp.json()["invoice_count"] == 0

    def test_tenant_isolation(self, as_tenant_b_owner, invoice):
        resp = as_tenant_b_owner.get("/api/reports/sales/")
        assert resp.status_code == 200
        assert resp.json()["invoice_count"] == 0


@pytest.mark.django_db
class TestPurchaseReport:
    def test_totals_and_by_status(self, as_tenant_a_owner, purchase):
        resp = as_tenant_a_owner.get("/api/reports/purchases/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["purchase_count"] == 1
        assert Decimal(str(data["total"])) == purchase.total
        assert any(row["status"] == "unpaid" for row in data["by_status"])

    def test_supplier_id_filter(self, as_tenant_a_owner, purchase, tenant_a):
        other_supplier = Supplier.objects.create(company=tenant_a, name="Someone Else")
        resp = as_tenant_a_owner.get(f"/api/reports/purchases/?supplier_id={other_supplier.id}")
        assert resp.status_code == 200
        assert resp.json()["purchase_count"] == 0


@pytest.mark.django_db
class TestExpenseReport:
    def test_by_category(self, as_tenant_a_owner, tenant_a, tenant_a_owner, expense_category):
        record_expense(
            company=tenant_a, user=tenant_a_owner, category=expense_category,
            date="2026-01-05", amount=Decimal("250.00"),
        )
        resp = as_tenant_a_owner.get("/api/reports/expenses/")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["total_amount"])) == Decimal("250.00")
        assert data["by_category"][0]["category__name"] == "Rent"

    def test_category_id_filter(self, as_tenant_a_owner, tenant_a, tenant_a_owner, expense_category):
        other_cat = ExpenseCategory.objects.create(company=tenant_a, name="Marketing")
        record_expense(company=tenant_a, user=tenant_a_owner, category=expense_category,
                        date="2026-01-05", amount=Decimal("100.00"))
        resp = as_tenant_a_owner.get(f"/api/reports/expenses/?category_id={other_cat.id}")
        assert resp.status_code == 200
        assert resp.json()["expense_count"] == 0


@pytest.mark.django_db
class TestTaxReport:
    def test_net_tax_payable(self, as_tenant_a_owner, invoice, purchase):
        resp = as_tenant_a_owner.get("/api/reports/tax/")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["tax_collected"])) == invoice.tax_amount
        assert Decimal(str(data["tax_paid"])) == purchase.tax_amount
        assert Decimal(str(data["net_tax_payable"])) == invoice.tax_amount - purchase.tax_amount


@pytest.mark.django_db
class TestStockReports:
    def test_stock_report_products_key(self, as_tenant_a_owner, purchase):
        """Bug: the view reads data['products'] but the service returned 'rows'."""
        resp = as_tenant_a_owner.get("/api/reports/stock/")
        assert resp.status_code == 200
        data = resp.json()
        assert "products" in data
        assert any(p["sku"] == "SKU-PUR" for p in data["products"])

    def test_stock_valuation(self, as_tenant_a_owner, purchase):
        resp = as_tenant_a_owner.get("/api/reports/stock-valuation/")
        assert resp.status_code == 200
        data = resp.json()
        assert "products" in data
        assert Decimal(str(data["total_valuation"])) > 0

    def test_non_stock_products_excluded(self, as_tenant_a_owner, tenant_a, sales_fixtures_factory):
        f = sales_fixtures_factory(tenant_a, sku="SKU-SERVICE")
        f["product"].is_stock_tracked = False
        f["product"].save(update_fields=["is_stock_tracked"])
        resp = as_tenant_a_owner.get("/api/reports/stock/")
        assert resp.status_code == 200
        assert not any(p["sku"] == "SKU-SERVICE" for p in resp.json()["products"])


@pytest.mark.django_db
class TestOutstandingReports:
    def test_customer_outstanding(self, as_tenant_a_owner, invoice):
        resp = as_tenant_a_owner.get("/api/reports/customer-outstanding/")
        assert resp.status_code == 200
        data = resp.json()
        assert "customers" in data
        assert Decimal(str(data["total_outstanding"])) == invoice.total

    def test_supplier_outstanding(self, as_tenant_a_owner, purchase):
        resp = as_tenant_a_owner.get("/api/reports/supplier-outstanding/")
        assert resp.status_code == 200
        data = resp.json()
        assert "suppliers" in data
        assert Decimal(str(data["total_outstanding"])) == purchase.total


@pytest.mark.django_db
class TestCashFlow:
    def test_invoice_alone_has_no_cash_movement(self, as_tenant_a_owner, invoice):
        """A credit sale posts to Accounts Receivable, not Cash — no cash-flow
        footprint until a payment is actually received."""
        resp = as_tenant_a_owner.get("/api/reports/cash-flow/")
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["net_cash_flow"])) == Decimal("0")

    def test_payment_and_expense_move_cash(
        self, as_tenant_a_owner, tenant_a, tenant_a_owner, invoice, expense_category,
    ):
        record_customer_payment(
            company=tenant_a, user=tenant_a_owner, customer=invoice.customer,
            amount=Decimal("100.00"), date="2026-01-16", invoice=invoice,
        )
        record_expense(
            company=tenant_a, user=tenant_a_owner, category=expense_category,
            date="2026-01-17", amount=Decimal("30.00"),
        )
        resp = as_tenant_a_owner.get("/api/reports/cash-flow/")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["total_inflow"])) == Decimal("100.00")
        assert Decimal(str(data["total_outflow"])) == Decimal("30.00")
        assert Decimal(str(data["net_cash_flow"])) == Decimal("70.00")
        sources = {row["source_type"]: row for row in data["by_source"]}
        assert Decimal(str(sources["customer_payment"]["inflow"])) == Decimal("100.00")
        assert Decimal(str(sources["expense"]["outflow"])) == Decimal("30.00")

    def test_date_range_excludes_out_of_range_activity(
        self, as_tenant_a_owner, tenant_a, tenant_a_owner, invoice,
    ):
        record_customer_payment(
            company=tenant_a, user=tenant_a_owner, customer=invoice.customer,
            amount=Decimal("100.00"), date="2026-01-16", invoice=invoice,
        )
        resp = as_tenant_a_owner.get(
            "/api/reports/cash-flow/?date_from=2026-02-01&date_to=2026-02-28"
        )
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["total_inflow"])) == Decimal("0")


@pytest.mark.django_db
class TestCsvExport:
    """Every report supports ?format=csv (Section 22 audit trail) — a
    smoke test per report shape (list-of-dicts vs single-row) is enough
    to catch the export crashing on the new dict shapes."""

    @pytest.mark.parametrize("path", [
        "/api/reports/sales/",
        "/api/reports/purchases/",
        "/api/reports/expenses/",
        "/api/reports/tax/",
        "/api/reports/stock/",
        "/api/reports/customer-outstanding/",
        "/api/reports/supplier-outstanding/",
        "/api/reports/cash-flow/",
    ])
    def test_csv_export_succeeds(self, as_tenant_a_owner, invoice, purchase, path):
        resp = as_tenant_a_owner.get(path, {"format": "csv"})
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")
