"""The charts on Overview, in the spirit of Zoho's dashboard: receivables and payables, sales over 12 months and 30
days, income against expense, top expenses, best-selling items and how customers pay. Every business type keeps its
sales on invoices (counter, restaurant and salon bills included), so one set of charts fits them all.

build(company) returns plain numbers; the template hands the series to Chart.js."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

ZERO = Decimal("0")


def _months(today, n=12):
    """First day of each of the last n months, oldest first."""
    first = today.replace(day=1)
    out = []
    for _i in range(n):
        out.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    return out[::-1]


def _by_month(qs, field, starts):
    rows = qs.filter(date__gte=starts[0]).annotate(m=TruncMonth("date")).values("m").annotate(t=Sum(field))
    got = {(r["m"].date() if hasattr(r["m"], "date") else r["m"]): r["t"] or ZERO for r in rows}
    return [got.get(s, ZERO) for s in starts]


def _change(now, before):
    """Percent change, or None when there is nothing to compare with."""
    if not before:
        return None
    return round(float((now - before) / before * 100))


def _dues(qs, today):
    """(total, current, overdue) still owed on bills that are not void or fully paid."""
    open_qs = qs.exclude(status__in=("void", "paid"))
    total = open_qs.aggregate(t=Sum(F("total") - F("amount_paid")))["t"] or ZERO
    overdue = open_qs.filter(due_date__lt=today).aggregate(t=Sum(F("total") - F("amount_paid")))["t"] or ZERO
    total, overdue = max(total, ZERO), max(overdue, ZERO)
    return {"total": total, "overdue": overdue, "current": max(total - overdue, ZERO),
            "overdue_pct": round(float(overdue / total * 100)) if total else 0}


def build(company, today=None):
    from apps.expenses.models import Expense
    from apps.purchases.models import Purchase
    from apps.sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine
    today = today or timezone.localdate()
    invoices = SalesInvoice.objects.for_company(company).exclude(status="void")
    expenses = Expense.objects.for_company(company)
    purchases = Purchase.objects.for_company(company).exclude(status="void")
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    same_day_last_month = min(today.day, last_month_end.day)

    def total(qs, field="total"):
        return qs.aggregate(t=Sum(field))["t"] or ZERO

    sales_today = total(invoices.filter(date=today))
    sales_yesterday = total(invoices.filter(date=today - timedelta(days=1)))
    sales_month = total(invoices.filter(date__gte=month_start))
    # compare the month so far with the same days of last month, so the 3rd isn't compared with a full month
    sales_last_month_to_date = total(invoices.filter(date__gte=last_month_start,
                                                     date__lte=last_month_start.replace(day=same_day_last_month)))
    sales_last_month = total(invoices.filter(date__gte=last_month_start, date__lte=last_month_end))
    expense_month = total(expenses.filter(date__gte=month_start), "amount") + total(purchases.filter(date__gte=month_start))

    starts = _months(today)
    sales_12 = _by_month(invoices, "total", starts)
    spend_12 = [a + b for a, b in zip(_by_month(expenses, "amount", starts), _by_month(purchases, "total", starts))]

    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    daily = {r["date"]: r["t"] for r in invoices.filter(date__gte=days[0]).values("date").annotate(t=Sum("total"))}

    top_items = list(
        SalesInvoiceLine.objects.filter(invoice__company=company, invoice__date__gte=month_start)
        .exclude(invoice__status="void").values("product__name")
        .annotate(amount=Sum("line_total"), qty=Sum("quantity")).order_by("-amount")[:5])
    top_spend = list(expenses.filter(date__gte=month_start).values("category__name")
                     .annotate(t=Sum("amount")).order_by("-t")[:5])
    methods = list(CustomerPayment.objects.for_company(company).filter(date__gte=month_start)
                   .values("method").annotate(t=Sum("amount")).order_by("-t")[:6])

    def num(values):
        return [float(v or 0) for v in values]

    return {
        "currency": company.default_currency,
        "summary": [
            {"label": _("Today's sales"), "value": sales_today, "change": _change(sales_today, sales_yesterday),
             "vs": _("vs yesterday"), "url": f"{reverse('webapp:sales_invoice_list')}?from={today:%Y-%m-%d}&to={today:%Y-%m-%d}"},
            {"label": _("This month's revenue"), "value": sales_month, "change": _change(sales_month, sales_last_month_to_date),
             "vs": _("vs same days last month"),
             "url": f"{reverse('webapp:sales_invoice_list')}?from={month_start:%Y-%m-%d}&to={today:%Y-%m-%d}"},
            {"label": _("Last month"), "value": sales_last_month, "change": None, "vs": "",
             "url": f"{reverse('webapp:sales_invoice_list')}?from={last_month_start:%Y-%m-%d}&to={last_month_end:%Y-%m-%d}"},
            {"label": _("Spent this month"), "value": expense_month, "change": None, "vs": _("expenses and purchases"),
             "url": reverse("webapp:expense_list")},
        ],
        "dues_cards": [
            (_("Total receivables"), _("Unpaid invoices"), _dues(invoices, today), reverse("webapp:receivables"),
             reverse("webapp:pos"), _("New bill")),
            (_("Total payables"), _("Unpaid supplier bills"), _dues(purchases, today), reverse("webapp:purchase_list"),
             reverse("webapp:purchase_add"), _("Record purchase")),
        ],
        "year_sales": sum(sales_12, ZERO),
        "year_spend": sum(spend_12, ZERO),
        "total30": sum((daily.get(d) or ZERO for d in days), ZERO),
        "series": {
            "months": [f"{s:%b %y}" for s in starts],
            "sales12": num(sales_12),
            "spend12": num(spend_12),
            "days": [f"{d:%d %b}" for d in days],
            "daily": num(daily.get(d) for d in days),
            "spendLabels": [r["category__name"] for r in top_spend],
            "spendValues": num(r["t"] for r in top_spend),
            "payLabels": [str(r["method"]).replace("_", " ").title() for r in methods],
            "payValues": num(r["t"] for r in methods),
        },
        "top_items": [{"name": r["product__name"].split(" — ")[-1], "amount": r["amount"] or ZERO, "qty": r["qty"] or 0,
                       "pct": round(float((r["amount"] or 0) / (top_items[0]["amount"] or 1) * 100))} for r in top_items],
    }
