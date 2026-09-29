from decimal import Decimal
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.utils import timezone

from apps.sales.models import SalesInvoice, SalesInvoiceLine
from apps.purchases.models import Purchase
from apps.expenses.models import Expense
from apps.inventory.models import Product, ProductBatch
from apps.banking.models import BankAccount


ZERO = Decimal("0")


def _sum(qs, field):
    return qs.aggregate(value=Sum(field))["value"] or ZERO


def dashboard_metrics(*, company, start_date=None, end_date=None, warehouse=None):
    today = timezone.localdate()
    start_date = start_date or today.replace(day=1)
    end_date = end_date or today
    sales = SalesInvoice.objects.for_company(company).filter(date__range=(start_date, end_date)).exclude(status="void")
    purchases = Purchase.objects.for_company(company).filter(date__range=(start_date, end_date))
    expenses = Expense.objects.for_company(company).filter(date__range=(start_date, end_date))
    if warehouse:
        sales = sales.filter(warehouse=warehouse)
    receivables = _sum(sales, "total") - _sum(sales, "amount_paid")
    payables = _sum(purchases, "total") - _sum(purchases, "amount_paid")
    overdue = sales.filter(due_date__lt=today).exclude(status="paid")
    low_stock = [p for p in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True) if p.current_stock(warehouse) <= p.reorder_level]
    near_expiry = ProductBatch.objects.for_company(company).filter(expiry_date__range=(today, today + timezone.timedelta(days=30)))
    top_products = list(SalesInvoiceLine.objects.filter(invoice__company=company, invoice__in=sales).values("product_id", "product__name").annotate(quantity=Sum("quantity"), revenue=Sum("line_total")).order_by("-revenue")[:10])
    top_customers = list(sales.values("customer_id", "customer__name").annotate(revenue=Sum("total")).order_by("-revenue")[:10])
    sales_trend = list(sales.values("date").annotate(value=Sum("total")).order_by("date"))
    expense_trend = list(expenses.values("date").annotate(value=Sum("amount")).order_by("date"))
    gross_sales = _sum(sales, "subtotal")
    cost_expr = ExpressionWrapper(F("quantity") * F("product__cost_price"), output_field=DecimalField(max_digits=18, decimal_places=2))
    estimated_cogs = SalesInvoiceLine.objects.filter(invoice__in=sales).aggregate(value=Sum(cost_expr))["value"] or ZERO
    return {
        "period": {"start": start_date, "end": end_date},
        "sales": _sum(sales, "total"), "purchases": _sum(purchases, "total"), "expenses": _sum(expenses, "amount"),
        "gross_profit_estimate": gross_sales - estimated_cogs,
        "gross_profit_definition": "invoice subtotal less current product cost; use ledger P&L for audited profit",
        "cash_bank_balance": _sum(BankAccount.objects.for_company(company).filter(is_active=True), "opening_balance"),
        "receivables": receivables, "payables": payables,
        "overdue": {"count": overdue.count(), "value": _sum(overdue, "total") - _sum(overdue, "amount_paid")},
        "low_stock": [{"id": p.id, "name": p.name, "quantity": str(p.current_stock(warehouse))} for p in low_stock[:50]],
        "near_expiry_count": near_expiry.count(), "top_products": top_products, "top_customers": top_customers,
        "sales_trend": sales_trend, "expense_trend": expense_trend,
    }
