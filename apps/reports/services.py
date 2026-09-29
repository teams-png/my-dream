"""
Cross-app reporting engine (Phase 0 Section 5 app list — "reports/ #
cross-app reporting engine"). Financial reports (P&L, Balance Sheet, Trial
Balance) live in apps.accounting.services since they read the ledger
directly; this module holds reports that aggregate across other apps
(sales, purchases, expenses, inventory) instead.

Phase 25: filled in the functions apps/reports/views.py has called since
it was written — cash_flow, purchase_report, expense_report, tax_report,
stock_valuation didn't exist here at all; sales_report/stock_report/
customer_outstanding/supplier_outstanding existed under different
names/shapes than the view expects. See PHASE25_NOTES.md.
"""
from decimal import Decimal
from django.db.models import Count, Sum


def sales_report(company, date_from=None, date_to=None, customer_id=None):
    from apps.sales.models import SalesInvoice

    qs = SalesInvoice.objects.for_company(company).exclude(status="void")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    totals = qs.aggregate(
        subtotal=Sum("subtotal"), tax=Sum("tax_amount"),
        total=Sum("total"), paid=Sum("amount_paid"),
    )
    by_status = list(
        qs.values("status").annotate(count=Count("id"), total=Sum("total")).order_by("status")
    )

    return {
        "invoice_count": qs.count(),
        "subtotal": totals["subtotal"] or Decimal("0"),
        "tax": totals["tax"] or Decimal("0"),
        "total": totals["total"] or Decimal("0"),
        "paid": totals["paid"] or Decimal("0"),
        "outstanding": (totals["total"] or Decimal("0")) - (totals["paid"] or Decimal("0")),
        "by_status": by_status,
        "invoices": list(qs.order_by("-date", "-id").values(
            "id", "invoice_number", "customer__name", "date", "total", "amount_paid", "status"
        )),
    }


def purchase_report(company, date_from=None, date_to=None, supplier_id=None):
    from apps.purchases.models import Purchase

    qs = Purchase.objects.for_company(company)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)

    totals = qs.aggregate(
        subtotal=Sum("subtotal"), tax=Sum("tax_amount"),
        total=Sum("total"), paid=Sum("amount_paid"),
    )
    by_status = list(
        qs.values("status").annotate(count=Count("id"), total=Sum("total")).order_by("status")
    )

    return {
        "purchase_count": qs.count(),
        "subtotal": totals["subtotal"] or Decimal("0"),
        "tax": totals["tax"] or Decimal("0"),
        "total": totals["total"] or Decimal("0"),
        "paid": totals["paid"] or Decimal("0"),
        "outstanding": (totals["total"] or Decimal("0")) - (totals["paid"] or Decimal("0")),
        "by_status": by_status,
        "purchases": list(qs.order_by("-date", "-id").values(
            "id", "bill_number", "supplier__name", "date", "total", "amount_paid", "status"
        )),
    }


def expense_report(company, date_from=None, date_to=None, category_id=None):
    from apps.expenses.models import Expense

    qs = Expense.objects.for_company(company)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if category_id:
        qs = qs.filter(category_id=category_id)

    total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    by_category = list(
        qs.values("category__name").annotate(total=Sum("amount")).order_by("-total")
    )

    return {
        "expense_count": qs.count(),
        "total_amount": total,
        "by_category": by_category,
        "expenses": list(qs.order_by("-date", "-id").values(
            "id", "category__name", "date", "amount", "description", "payment_method"
        )),
    }


def tax_report(company, date_from=None, date_to=None):
    """
    Simple output-tax vs input-tax summary — tax collected on sales minus
    tax paid on purchases, over the period. Not a substitute for a real
    VAT/return filing report, just what a small business needs to see its
    net tax position at a glance.
    """
    from apps.sales.models import SalesInvoice
    from apps.purchases.models import Purchase

    sales_qs = SalesInvoice.objects.for_company(company).exclude(status="void")
    purchase_qs = Purchase.objects.for_company(company)
    if date_from:
        sales_qs = sales_qs.filter(date__gte=date_from)
        purchase_qs = purchase_qs.filter(date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(date__lte=date_to)
        purchase_qs = purchase_qs.filter(date__lte=date_to)

    tax_collected = sales_qs.aggregate(t=Sum("tax_amount"))["t"] or Decimal("0")
    tax_paid = purchase_qs.aggregate(t=Sum("tax_amount"))["t"] or Decimal("0")
    from apps.sales.models import SalesInvoiceLine
    from apps.purchases.models import PurchaseLine
    sales_by_code = SalesInvoiceLine.objects.filter(invoice__in=sales_qs, tax_code__isnull=False).values(
        "tax_code__code", "tax_code__classification"
    ).annotate(tax=Sum("tax_amount"), taxable=Sum("taxable_amount"))
    purchase_by_code = PurchaseLine.objects.filter(purchase__in=purchase_qs, tax_code__isnull=False).values(
        "tax_code__code", "tax_code__classification"
    ).annotate(tax=Sum("tax_amount"), taxable=Sum("taxable_amount"))

    return {
        "date_from": date_from,
        "date_to": date_to,
        "tax_collected": tax_collected,
        "tax_paid": tax_paid,
        "net_tax_payable": tax_collected - tax_paid,
        "sales_by_tax_code": list(sales_by_code),
        "purchases_by_tax_code": list(purchase_by_code),
    }


def _resolve_warehouse(company, warehouse_id):
    if not warehouse_id:
        return None
    from apps.inventory.models import Warehouse
    return Warehouse.objects.for_company(company).filter(pk=warehouse_id).first()


def _stock_rows(company, warehouse=None):
    from apps.inventory.models import Product

    products = Product.objects.for_company(company).filter(
        is_active=True, is_stock_tracked=True,
    ).select_related("category", "unit")
    rows = []
    total_valuation = Decimal("0")

    for product in products:
        qty = product.current_stock(warehouse)
        valuation = Decimal(qty) * product.cost_price
        total_valuation += valuation
        rows.append({
            "product": product.name,
            "sku": product.sku,
            "category": product.category.name if product.category else None,
            "unit": product.unit.name,
            "current_stock": qty,
            "reorder_level": product.reorder_level,
            "below_reorder": qty <= product.reorder_level,
            "cost_price": product.cost_price,
            "valuation": valuation,
        })

    return rows, total_valuation


def stock_report(company, warehouse_id=None):
    """
    Current stock per product, derived from the StockMovement ledger
    (never a stored counter — Phase 0 Section 18), plus stock valuation
    at cost price.
    """
    warehouse = _resolve_warehouse(company, warehouse_id)
    rows, total_valuation = _stock_rows(company, warehouse)
    return {"products": rows, "total_valuation": total_valuation}


def stock_valuation(company):
    """
    Company-wide valuation-only view of the same stock data stock_report
    exposes (no warehouse filter — this is the "how much is tied up in
    inventory overall" figure, not a per-warehouse operational report).
    """
    rows, total_valuation = _stock_rows(company)
    return {"products": rows, "total_valuation": total_valuation}


def customer_outstanding(company):
    from apps.customers.models import Customer
    from apps.sales.models import SalesInvoice

    rows = []
    total_outstanding = Decimal("0")
    for customer in Customer.objects.for_company(company).filter(is_active=True):
        agg = SalesInvoice.objects.for_company(company).filter(customer=customer).exclude(
            status="void"
        ).aggregate(total=Sum("total"), paid=Sum("amount_paid"))
        outstanding = (agg["total"] or Decimal("0")) - (agg["paid"] or Decimal("0"))
        if outstanding:
            rows.append({"customer_id": customer.id, "customer": customer.name, "outstanding": outstanding})
            total_outstanding += outstanding

    return {"customers": rows, "total_outstanding": total_outstanding}


def supplier_outstanding(company):
    from apps.suppliers.models import Supplier
    from apps.purchases.models import Purchase

    rows = []
    total_outstanding = Decimal("0")
    for supplier in Supplier.objects.for_company(company).filter(is_active=True):
        agg = Purchase.objects.for_company(company).filter(supplier=supplier).aggregate(
            total=Sum("total"), paid=Sum("amount_paid")
        )
        outstanding = (agg["total"] or Decimal("0")) - (agg["paid"] or Decimal("0"))
        if outstanding:
            rows.append({"supplier_id": supplier.id, "supplier": supplier.name, "outstanding": outstanding})
            total_outstanding += outstanding

    return {"suppliers": rows, "total_outstanding": total_outstanding}


# Journal source_types that represent money actually moving in/out of the
# business (as opposed to e.g. a sale made entirely on credit, which posts
# to Accounts Receivable, not Cash/Bank, and correctly has no cash-flow
# footprint until CustomerPayment is recorded against it).
_CASH_ACCOUNT_CODES = ("1000", "1010")  # Cash, Bank — see DEFAULT_CHART_OF_ACCOUNTS


def cash_flow(company, date_from=None, date_to=None):
    """
    Net movement through the Cash and Bank accounts over a period, grouped
    by the journal entry's source_type. Derived from JournalLine activity
    only (never re-summed from SalesInvoice/Purchase/Expense directly) so
    it always agrees with the ledger, same principle as
    accounting.services.profit_and_loss.
    """
    from apps.accounting.models import Account, JournalLine

    cash_accounts = Account.objects.for_company(company).filter(
        code__in=_CASH_ACCOUNT_CODES, is_active=True,
    )

    qs = JournalLine.objects.filter(account__in=cash_accounts, journal_entry__is_void=False)
    if date_from:
        qs = qs.filter(journal_entry__date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__date__lte=date_to)

    by_source = list(
        qs.values("journal_entry__source_type").annotate(
            inflow=Sum("debit"), outflow=Sum("credit"),
        ).order_by("journal_entry__source_type")
    )
    for row in by_source:
        row["source_type"] = row.pop("journal_entry__source_type") or "manual"
        row["inflow"] = row["inflow"] or Decimal("0")
        row["outflow"] = row["outflow"] or Decimal("0")
        row["net"] = row["inflow"] - row["outflow"]

    totals = qs.aggregate(inflow=Sum("debit"), outflow=Sum("credit"))
    total_inflow = totals["inflow"] or Decimal("0")
    total_outflow = totals["outflow"] or Decimal("0")

    opening_balance = Decimal("0")
    if date_from:
        opening_qs = JournalLine.objects.filter(
            account__in=cash_accounts, journal_entry__is_void=False, journal_entry__date__lt=date_from,
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        opening_balance = (opening_qs["debit"] or Decimal("0")) - (opening_qs["credit"] or Decimal("0"))

    return {
        "date_from": date_from,
        "date_to": date_to,
        "opening_balance": opening_balance,
        "by_source": by_source,
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "net_cash_flow": total_inflow - total_outflow,
        "closing_balance": opening_balance + total_inflow - total_outflow,
    }
